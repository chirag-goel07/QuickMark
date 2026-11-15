// Attendance statistics, advice, streaks and sorting.
//   OOP : AttendanceStats (value class with behaviour), NaturalKey (comparable object, operator<).
//   DSA : stable merge sort on an index array (std::stable_sort), tokenising scan, ceiling division.
#pragma once
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <numeric>
#include <string>
#include <vector>

namespace qm {

// Round to 1 decimal exactly like Python's round(x, 1): correctly rounded from the real binary value.
inline double round1(double x) {
    char buf[64];
    std::snprintf(buf, sizeof buf, "%.1f", x);
    return std::strtod(buf, nullptr);
}

struct Advice {
    enum Kind { None = 0, Ok = 1, BelowWithCount = 2, BelowNoCount = 3 } kind = None;
    long long count = 0;      // Ok: classes that can still be missed | BelowWithCount: classes in a row needed
};

class AttendanceStats {
public:
    AttendanceStats(long long present, long long total) : present_(present), total_(total) {}

    bool has_data() const { return total_ > 0; }
    // 1 decimal, e.g. 83.3. Only meaningful when has_data().
    double percentage() const { return round1(100.0 * static_cast<double>(present_) / static_cast<double>(total_)); }

    // How many classes can still be missed (above threshold) or must be attended in a row (below it).
    Advice advice(long long threshold) const {
        Advice a;
        if (total_ == 0) return a;
        const long long have = 100 * present_, need = threshold * total_;
        if (have >= need) {
            a.kind = Advice::Ok;
            a.count = threshold > 0 ? (have - need) / threshold : 0;
            return a;
        }
        if (threshold >= 100) { a.kind = Advice::BelowNoCount; return a; }
        const long long gap = need - have, per_class = 100 - threshold;
        a.kind = Advice::BelowWithCount;
        a.count = (gap + per_class - 1) / per_class;                        // ceiling division
        return a;
    }

private:
    long long present_, total_;
};

// Indices that would sort `values` ascending. Stable, so equal values keep their original order.
inline std::vector<int> order_ascending(const std::vector<double>& values) {
    std::vector<int> idx(values.size());
    std::iota(idx.begin(), idx.end(), 0);
    std::stable_sort(idx.begin(), idx.end(), [&](int a, int b) { return values[a] < values[b]; });
    return idx;
}

// Natural order for roll numbers: "2" < "10", "A9" < "A10", case-insensitive.
// Splits a string into alternating text / number chunks (same shape as Python re.split(r"(\d+)", s)).
class NaturalKey {
public:
    explicit NaturalKey(const std::string& s) {
        std::string cur;
        bool in_digits = false;
        chunks_.push_back({false, ""});
        for (char c : s) {
            bool d = (c >= '0' && c <= '9');
            if (d != in_digits) {
                chunks_.back().text = finish(cur, in_digits);
                cur.clear();
                chunks_.push_back({d, ""});
                in_digits = d;
            }
            cur.push_back(c);
        }
        chunks_.back().text = finish(cur, in_digits);
        if (in_digits) chunks_.push_back({false, ""});                      // always end on a text chunk
    }

    bool operator<(const NaturalKey& o) const { return compare(o) < 0; }

    int compare(const NaturalKey& o) const {
        std::size_t n = std::min(chunks_.size(), o.chunks_.size());
        for (std::size_t i = 0; i < n; ++i) {
            const std::string &a = chunks_[i].text, &b = o.chunks_[i].text;
            int c;
            if (chunks_[i].is_number) {                                     // compare as integers of any size
                c = a.size() != b.size() ? (a.size() < b.size() ? -1 : 1) : a.compare(b);
            } else {
                c = a.compare(b);
            }
            if (c != 0) return c < 0 ? -1 : 1;
        }
        if (chunks_.size() == o.chunks_.size()) return 0;
        return chunks_.size() < o.chunks_.size() ? -1 : 1;
    }

private:
    struct Chunk { bool is_number; std::string text; };

    static std::string finish(const std::string& raw, bool is_number) {
        if (is_number) {                                                    // drop leading zeros: "007" == "7"
            std::size_t k = raw.find_first_not_of('0');
            return k == std::string::npos ? "0" : raw.substr(k);
        }
        std::string low = raw;
        for (char& c : low) if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
        return low;
    }

    std::vector<Chunk> chunks_;
};

inline std::vector<int> natural_order(const std::vector<std::string>& items) {
    std::vector<NaturalKey> keys;
    keys.reserve(items.size());
    for (const auto& s : items) keys.emplace_back(s);
    std::vector<int> idx(items.size());
    std::iota(idx.begin(), idx.end(), 0);
    std::stable_sort(idx.begin(), idx.end(), [&](int a, int b) { return keys[a] < keys[b]; });
    return idx;
}

// Newest first: number of consecutive "present" at the start.
inline int leading_streak(const int* is_present, int n) {
    int s = 0;
    while (s < n && is_present[s]) ++s;
    return s;
}

}  // namespace qm
