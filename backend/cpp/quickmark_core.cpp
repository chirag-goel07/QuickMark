// C interface of the QuickMark C++ core. Flask (Python) calls these through ctypes - see services/core.py.
// Plain C types only (numbers, UTF-8 strings, arrays) so it works with any compiler and any Python version.
#include <cstring>
#include <string>
#include <vector>

#include "csv_writer.hpp"
#include "face.hpp"
#include "rate_limiter.hpp"
#include "stats.hpp"

#if defined(_WIN32)
#define QM_API extern "C" __declspec(dllexport)
#else
#define QM_API extern "C" __attribute__((visibility("default")))
#endif

namespace {
qm::SlidingWindowLimiter g_limiter;      // one limiter and one lock-out table per server process
qm::LockoutTracker g_lockout;
}  // namespace

QM_API const char* qm_version() { return "quickmark_core 1.0 (C++17)"; }

// ---------------------------------------------------------------- rate limiter
QM_API int qm_rl_allow(const char* key, int limit, double window, double now) {
    return g_limiter.allow(key ? key : "", limit, window, now) ? 1 : 0;
}
QM_API void qm_rl_reset() { g_limiter.reset(); }
QM_API int qm_rl_keys() { return static_cast<int>(g_limiter.tracked_keys()); }

// ---------------------------------------------------------------- face
QM_API int qm_face_validate(const double* v, int n) { return qm::FaceDescriptor::is_valid(v, n) ? 1 : 0; }

QM_API double qm_face_distance(const double* a, const double* b, int n) {
    return qm::FaceDescriptor(a, n).distance(qm::FaceDescriptor(b, n));
}

// flat = count*dim doubles. Returns 1 and writes the average to out_avg, 0 if the captures are not the same face.
QM_API int qm_face_enroll(const double* flat, int count, int dim, double consistency, double* out_avg) {
    if (!flat || count < 1 || dim < 1) return -1;
    std::vector<qm::FaceDescriptor> caps;
    for (int i = 0; i < count; ++i) caps.emplace_back(flat + static_cast<std::size_t>(i) * dim, dim);
    if (!qm::captures_consistent(caps, consistency)) return 0;
    qm::FaceDescriptor avg = qm::FaceDescriptor::mean(caps);
    for (int k = 0; k < dim; ++k) out_avg[k] = avg[k];
    return 1;
}

QM_API int qm_lock_check(long long id, double now, double window, int max_fails) {
    return g_lockout.is_locked(id, now, window, max_fails) ? 1 : 0;
}
QM_API void qm_lock_fail(long long id, double now) { g_lockout.record_failure(id, now); }
QM_API void qm_lock_clear(long long id) { g_lockout.clear(id); }
QM_API int qm_lock_count(long long id) { return g_lockout.failures(id); }
QM_API void qm_lock_reset_all() { g_lockout.reset_all(); }
QM_API void qm_lock_seed(long long id, double t, int n) {      // used by the tests to fake old failures
    for (int i = 0; i < n; ++i) g_lockout.record_failure(id, t);
}

// ---------------------------------------------------------------- statistics
// Returns 1 and writes the percentage (1 decimal) when total > 0, else 0.
QM_API int qm_percent(long long present, long long total, double* out) {
    qm::AttendanceStats s(present, total);
    if (!s.has_data()) return 0;
    *out = s.percentage();
    return 1;
}

// Returns the kind: 0 no data, 1 ok (count = classes that can be missed), 2 below (count = classes needed), 3 below, no count.
QM_API int qm_advice(long long present, long long total, long long threshold, long long* count) {
    qm::Advice a = qm::AttendanceStats(present, total).advice(threshold);
    *count = a.count;
    return static_cast<int>(a.kind);
}

QM_API void qm_order_ascending(const double* values, int n, int* out_idx) {
    std::vector<double> v(values, values + n);
    std::vector<int> idx = qm::order_ascending(v);
    for (int i = 0; i < n; ++i) out_idx[i] = idx[i];
}

QM_API void qm_natural_order(const char* const* items, int n, int* out_idx) {
    std::vector<std::string> v;
    for (int i = 0; i < n; ++i) v.emplace_back(items[i] ? items[i] : "");
    std::vector<int> idx = qm::natural_order(v);
    for (int i = 0; i < n; ++i) out_idx[i] = idx[i];
}

QM_API int qm_streak(const int* is_present, int n) { return qm::leading_streak(is_present, n); }

// ---------------------------------------------------------------- CSV
// Writes the safe version of one text cell into out (cap bytes). Returns the bytes needed (without the final 0).
QM_API int qm_csv_sanitize(const char* cell, char* out, int cap) {
    std::string s = qm::sanitize_cell(cell ? cell : "");
    if (out && cap > 0) {
        int n = static_cast<int>(s.size()) < cap - 1 ? static_cast<int>(s.size()) : cap - 1;
        std::memcpy(out, s.data(), n);
        out[n] = 0;
    }
    return static_cast<int>(s.size());
}

QM_API void* qm_csv_new() { return new qm::CsvWriter(true); }
QM_API void qm_csv_add_row(void* h, const char* const* cells, const int* is_text, int n) {
    std::vector<qm::Cell> row;
    for (int i = 0; i < n; ++i) row.push_back({cells[i] ? cells[i] : "", is_text[i] != 0});
    static_cast<qm::CsvWriter*>(h)->add_row(row);
}
QM_API const char* qm_csv_data(void* h, int* len) {
    const std::string& s = static_cast<qm::CsvWriter*>(h)->str();
    *len = static_cast<int>(s.size());
    return s.data();
}
QM_API void qm_csv_free(void* h) { delete static_cast<qm::CsvWriter*>(h); }
