#ifndef slic3r_CloudProfileSnapshot_hpp_
#define slic3r_CloudProfileSnapshot_hpp_

#include <map>
#include <string>
#include <cstdint>

namespace Slic3r {

using CloudPresetSnapshot = std::map<std::string, std::map<std::string, std::string>>;

struct CloudProfileSession {
    std::string user_id;
    std::uint64_t revision = 0;
    bool logged_in = false;

    bool matches(const CloudProfileSession &current) const
    {
        return logged_in && current.logged_in && !user_id.empty() &&
               user_id == current.user_id && revision == current.revision;
    }
};

// A complete library may authorize deletions, so parsing must not publish partial results.
CloudPresetSnapshot tinmanx_parse_cloud_profile_snapshot(unsigned int http_status,
                                                        const std::string &body,
                                                        const std::string &user_id);

} // namespace Slic3r

#endif
