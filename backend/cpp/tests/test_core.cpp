// Native tests for the C++ core:  python build_cpp.py --test
#include <cassert>
#include <cstdio>
#include <iostream>

#include "../csv_writer.hpp"
#include "../face.hpp"
#include "../rate_limiter.hpp"
#include "../stats.hpp"

static int passed = 0;
#define CHECK(c) do { if (!(c)) { std::printf("FAIL line %d: %s\n", __LINE__, #c); return 1; } ++passed; } while (0)

int main() {
    using namespace qm;

    // rate limiter: 3 per 10s window
    SlidingWindowLimiter rl;
    CHECK(rl.allow("a", 3, 10, 100) && rl.allow("a", 3, 10, 101) && rl.allow("a", 3, 10, 102));
    CHECK(!rl.allow("a", 3, 10, 103));
    CHECK(rl.allow("b", 3, 10, 103));                  // other key is independent
    CHECK(rl.allow("a", 3, 10, 111));                  // the 100s hit has left the window
    rl.reset();
    CHECK(rl.tracked_keys() == 0);

    // face
    std::vector<double> a(128, 0.1), b(128, 0.1);
    b[0] = 0.4;
    CHECK(FaceDescriptor::is_valid(a.data(), 128) && !FaceDescriptor::is_valid(a.data(), 127));
    a[5] = 9; CHECK(!FaceDescriptor::is_valid(a.data(), 128)); a[5] = 0.1;
    FaceDescriptor fa(a.data(), 128), fb(b.data(), 128);
    CHECK(std::fabs((fa - fb) - 0.3) < 1e-12);
    FaceDescriptor m = FaceDescriptor::mean({fa, fb});
    CHECK(std::fabs(m[0] - 0.25) < 1e-12);
    CHECK(captures_consistent({fa, fb}, 0.45) && !captures_consistent({fa, fb}, 0.2));
    LockoutTracker lk;
    for (int i = 0; i < 5; ++i) lk.record_failure(7, 1000 + i);
    CHECK(lk.is_locked(7, 1010, 60, 5));
    CHECK(!lk.is_locked(7, 1100, 60, 5));              // wait is over
    lk.record_failure(7, 1100); lk.clear(7);
    CHECK(lk.failures(7) == 0);

    // stats
    CHECK(AttendanceStats(1, 6).percentage() == 16.7);
    CHECK(AttendanceStats(1, 16).percentage() == 6.2);           // 6.25 -> half to even, same as Python round()
    CHECK(AttendanceStats(75, 100).advice(75).kind == Advice::Ok);
    CHECK(AttendanceStats(8, 10).advice(75).count == 0);         // 80% vs 75: (800-750)/75 = 0
    CHECK(AttendanceStats(9, 10).advice(75).count == 2);         // (900-750)/75 = 2
    Advice below = AttendanceStats(5, 10).advice(75);            // need ceil((750-500)/25) = 10
    CHECK(below.kind == Advice::BelowWithCount && below.count == 10);
    CHECK(AttendanceStats(5, 10).advice(100).kind == Advice::BelowNoCount);
    CHECK(AttendanceStats(0, 0).advice(75).kind == Advice::None);
    std::vector<double> pct = {50, 20, 50, 10};
    CHECK((order_ascending(pct) == std::vector<int>{3, 1, 0, 2}));          // stable for the two 50s
    std::vector<std::string> rolls = {"21CS10", "21CS2", "A10", "a9", "007", "7", "10", "2", ""};
    std::vector<int> o = natural_order(rolls);
    std::vector<std::string> sorted;
    for (int i : o) sorted.push_back(rolls[i]);
    CHECK((sorted == std::vector<std::string>{"", "2", "007", "7", "10", "21CS2", "21CS10", "a9", "A10"}));
    int flags[] = {1, 1, 0, 1};
    CHECK(leading_streak(flags, 4) == 2);

    // csv
    CHECK(sanitize_cell("=CMD()") == "'=CMD()" && sanitize_cell("Asha") == "Asha" && sanitize_cell("-1x") == "'-1x");
    CsvWriter w(false);
    w.add_row({{"Roll", true}, {"Name, Jr", true}, {"-5", false}, {"say \"hi\"", true}, {"@x", true}});
    CHECK(w.str() == "Roll,\"Name, Jr\",-5,\"say \"\"hi\"\"\",'@x\r\n");

    std::printf("all %d C++ checks passed\n", passed);
    return 0;
}
