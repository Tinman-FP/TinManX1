#ifndef slic3r_MoonrakerStorage_hpp_
#define slic3r_MoonrakerStorage_hpp_

#include <string>

#include <boost/property_tree/ptree.hpp>

namespace Slic3r::MoonrakerStorage {

inline bool is_printable_root(const std::string &root, const std::string &permissions)
{
    return root == "gcodes" && permissions.find('w') != std::string::npos;
}

inline std::string print_root(const std::string & /*requested_root*/)
{
    return "gcodes";
}

inline std::string uploaded_path(const boost::property_tree::ptree &response, const std::string &fallback)
{
    if (const auto path = response.get_optional<std::string>("result.item.path"); path && !path->empty())
        return *path;
    if (const auto path = response.get_optional<std::string>("item.path"); path && !path->empty())
        return *path;
    return fallback;
}

} // namespace Slic3r::MoonrakerStorage

#endif
