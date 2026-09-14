#pragma once

#include <boost/filesystem.hpp>
#include <boost/nowide/fstream.hpp>
#include <boost/uuid/name_generator_sha1.hpp>
#include <boost/uuid/uuid_io.hpp>
#include "libslic3r/Utils.hpp"

namespace Slic3r {

// Project paths are keys only. Reading this cache must never stat/open a
// project: cloud hydration or a disconnected volume can block indefinitely.
class RecentProjectThumbnailCache {
public:
    explicit RecentProjectThumbnailCache(boost::filesystem::path directory) : m_directory(std::move(directory)) {}

    std::string read(const std::string &project) const
    {
        boost::nowide::ifstream input(path_for(project).string(), std::ios::binary | std::ios::ate);
        if (!input) return {};
        const auto length = input.tellg();
        if (length < 8 || length > max_bytes) return {};
        std::string bytes(static_cast<size_t>(length), '\0');
        input.seekg(0);
        input.read(bytes.data(), static_cast<std::streamsize>(bytes.size()));
        return input && is_png(bytes) ? bytes : std::string();
    }

    void write(const std::string &project, const std::string &bytes) const
    {
        if (bytes.size() > max_bytes || !is_png(bytes)) return;
        boost::system::error_code ec;
        boost::filesystem::create_directories(m_directory, ec);
        if (ec) return;
        const auto target = path_for(project);
        const auto temporary = m_directory / boost::filesystem::unique_path("%%%%-%%%%-%%%%.tmp");
        {
            boost::nowide::ofstream output(temporary.string(), std::ios::binary | std::ios::trunc);
            output.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
            output.close();
            if (!output) {
                boost::filesystem::remove(temporary, ec);
                return;
            }
        }
        if (rename_file(temporary.string(), target.string()))
            boost::filesystem::remove(temporary, ec);
    }

private:
    static constexpr size_t max_bytes = 2 * 1024 * 1024;
    boost::filesystem::path m_directory;

    static bool is_png(const std::string &bytes)
    {
        return bytes.size() >= 8 && bytes.compare(0, 8, "\x89PNG\r\n\x1a\n", 8) == 0;
    }

    boost::filesystem::path path_for(const std::string &project) const
    {
        const auto key = boost::uuids::name_generator_sha1(boost::uuids::ns::url())(project);
        return m_directory / (boost::uuids::to_string(key) + ".png");
    }
};

} // namespace Slic3r
