// CSV builder with spreadsheet-formula-injection protection.
//   OOP : CsvWriter (encapsulated buffer, RAII-owned by a handle in the C API).
// Output format matches Python's csv module (comma, \r\n, quote only when needed) and starts with a UTF-8 BOM.
#pragma once
#include <string>
#include <vector>

namespace qm {

struct Cell {
    std::string text;
    bool is_text;      // numbers are never "defused": -5 must stay a number
};

// A text cell starting with = + - @ TAB CR would be RUN by Excel; a leading apostrophe makes it plain text.
inline std::string sanitize_cell(const std::string& s) {
    if (!s.empty() && (s[0] == '=' || s[0] == '+' || s[0] == '-' || s[0] == '@' || s[0] == '\t' || s[0] == '\r'))
        return "'" + s;
    return s;
}

class CsvWriter {
public:
    explicit CsvWriter(bool bom = true) : out_(bom ? "\xEF\xBB\xBF" : "") {}

    void add_row(const std::vector<Cell>& row) {
        for (std::size_t i = 0; i < row.size(); ++i) {
            if (i) out_ += ',';
            out_ += quote(row[i].is_text ? sanitize_cell(row[i].text) : row[i].text, row.size() == 1);
        }
        out_ += "\r\n";
    }

    const std::string& str() const { return out_; }

private:
    static std::string quote(const std::string& f, bool only_field) {
        bool need = (only_field && f.empty()) || f.find_first_of(",\"\r\n") != std::string::npos;
        if (!need) return f;
        std::string q = "\"";
        for (char c : f) { if (c == '"') q += '"'; q += c; }
        return q + "\"";
    }

    std::string out_;
};

}  // namespace qm
