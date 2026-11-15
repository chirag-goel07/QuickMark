// Sliding-window rate limiter.
//   OOP : encapsulation (state is private), thread-safe through an internal mutex.
//   DSA : hash map (unordered_map) key -> deque of timestamps, oldest first.
// Replaces the old services/ratelimit.py logic.
#pragma once
#include <algorithm>
#include <cstddef>
#include <deque>
#include <mutex>
#include <string>
#include <unordered_map>

namespace qm {

class SlidingWindowLimiter {
public:
    // true if `key` did fewer than `limit` things in the last `window` seconds; records this one.
    bool allow(const std::string& key, int limit, double window, double now) {
        std::lock_guard<std::mutex> lock(mu_);
        std::deque<double>& q = hits_[key];
        q.erase(std::remove_if(q.begin(), q.end(), [&](double t) { return now - t >= window; }), q.end());
        if (static_cast<int>(q.size()) >= limit) return false;      // pruned list stays stored
        q.push_back(now);
        if (hits_.size() > kMaxKeys) purge(now, window);            // keep memory small
        return true;
    }

    void reset() {
        std::lock_guard<std::mutex> lock(mu_);
        hits_.clear();
    }

    std::size_t tracked_keys() const {
        std::lock_guard<std::mutex> lock(mu_);
        return hits_.size();
    }

private:
    static constexpr std::size_t kMaxKeys = 5000;

    void purge(double now, double window) {                         // caller holds the lock
        for (auto it = hits_.begin(); it != hits_.end();) {
            const std::deque<double>& v = it->second;
            it = (v.empty() || now - v.back() > window) ? hits_.erase(it) : std::next(it);
        }
    }

    mutable std::mutex mu_;
    std::unordered_map<std::string, std::deque<double>> hits_;
};

}  // namespace qm
