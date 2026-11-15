// Face descriptor maths + wrong-face lock-out.
//   OOP : value class FaceDescriptor (encapsulated vector, operator-, named constructors), LockoutTracker.
//   DSA : vector maths (Euclidean distance, mean), pairwise comparison, hash map id -> deque of failure times.
// The browser sends 128 numbers; no photo ever reaches the server. Replaces the maths in services/face.py.
#pragma once
#include <cmath>
#include <cstddef>
#include <deque>
#include <mutex>
#include <unordered_map>
#include <vector>

namespace qm {

class FaceDescriptor {
public:
    static constexpr int kDim = 128;
    static constexpr double kMaxAbs = 5.0;

    FaceDescriptor() = default;
    FaceDescriptor(const double* data, int n) : v_(data, data + n) {}

    // 128 finite numbers, each between -5 and 5.
    static bool is_valid(const double* data, int n) {
        if (n != kDim) return false;
        for (int i = 0; i < n; ++i)
            if (!std::isfinite(data[i]) || std::fabs(data[i]) > kMaxAbs) return false;
        return true;
    }

    std::size_t size() const { return v_.size(); }
    double operator[](std::size_t i) const { return v_[i]; }

    // Euclidean distance between two descriptors.
    double distance(const FaceDescriptor& o) const {
        double s = 0.0;
        for (std::size_t i = 0; i < v_.size() && i < o.v_.size(); ++i) {
            double d = v_[i] - o.v_[i];
            s += d * d;
        }
        return std::sqrt(s);
    }
    double operator-(const FaceDescriptor& o) const { return distance(o); }   // "a - b" = how far apart

    // Element-wise average of several descriptors (the enrolled face).
    static FaceDescriptor mean(const std::vector<FaceDescriptor>& all) {
        FaceDescriptor out;
        if (all.empty()) return out;
        out.v_.assign(all[0].v_.size(), 0.0);
        for (const auto& f : all)
            for (std::size_t k = 0; k < out.v_.size(); ++k) out.v_[k] += f.v_[k];
        for (double& x : out.v_) x /= static_cast<double>(all.size());
        return out;
    }

    const std::vector<double>& values() const { return v_; }

private:
    std::vector<double> v_;
};

// Enrollment captures must all look like the same person: every PAIR within `limit` of each other. O(k^2) pairs.
inline bool captures_consistent(const std::vector<FaceDescriptor>& caps, double limit) {
    for (std::size_t i = 0; i < caps.size(); ++i)
        for (std::size_t j = i + 1; j < caps.size(); ++j)
            if (caps[i].distance(caps[j]) > limit) return false;
    return true;
}

// Per-student sliding window of wrong-face attempts. Too many inside the window = locked out.
class LockoutTracker {
public:
    bool is_locked(long long id, double now, double window, int max_fails) {
        std::lock_guard<std::mutex> lock(mu_);
        auto& q = fails_[id];
        while (!q.empty() && now - q.front() > window) q.pop_front();
        return static_cast<int>(q.size()) >= max_fails;
    }
    void record_failure(long long id, double now) {
        std::lock_guard<std::mutex> lock(mu_);
        fails_[id].push_back(now);
    }
    void clear(long long id) {
        std::lock_guard<std::mutex> lock(mu_);
        fails_.erase(id);
    }
    int failures(long long id) const {
        std::lock_guard<std::mutex> lock(mu_);
        auto it = fails_.find(id);
        return it == fails_.end() ? 0 : static_cast<int>(it->second.size());
    }
    void reset_all() {
        std::lock_guard<std::mutex> lock(mu_);
        fails_.clear();
    }

private:
    mutable std::mutex mu_;
    std::unordered_map<long long, std::deque<double>> fails_;
};

}  // namespace qm
