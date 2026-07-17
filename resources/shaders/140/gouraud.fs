#version 140

const vec3 ZERO = vec3(0.0, 0.0, 0.0);
//BBS: add grey and orange
//const vec3 GREY = vec3(0.9, 0.9, 0.9);
const vec3 ORANGE = vec3(0.8, 0.4, 0.0);
const vec3 LightRed = vec3(0.78, 0.0, 0.0);
const vec3 LightBlue = vec3(0.73, 1.0, 1.0);
const float EPSILON = 0.0001;

struct PrintVolumeDetection
{
	// 0 = rectangle, 1 = circle, 2 = custom, 3 = invalid
	int type;
    // type = 0 (rectangle):
    // x = min.x, y = min.y, z = max.x, w = max.y
    // type = 1 (circle):
    // x = center.x, y = center.y, z = radius
	vec4 xy_data;
    // x = min z, y = max z
	vec2 z_data;
};

struct SlopeDetection
{
    bool actived;
	float normal_z;
    mat3 volume_world_normal_matrix;
};

struct StrengthLens
{
    bool enabled;
    vec3 axis_strength;
    vec3 bbox_min;
    vec3 bbox_size;
    vec3 load_axis;
    vec3 weak_axis;
    float load_span_weight;
    float surface_weight;
    float layer_penalty_weight;
};

uniform vec4 uniform_color;
uniform bool use_color_clip_plane;
uniform vec4 uniform_color_clip_plane_1;
uniform vec4 uniform_color_clip_plane_2;
uniform SlopeDetection slope;
uniform StrengthLens strength_lens;

//BBS: add outline_color
uniform bool is_outline;
uniform sampler2D depth_tex;
uniform vec2 screen_size;

#ifdef ENABLE_ENVIRONMENT_MAP
    uniform sampler2D environment_tex;
    uniform bool use_environment_tex;
#endif // ENABLE_ENVIRONMENT_MAP

uniform PrintVolumeDetection print_volume;

uniform float z_far;
uniform float z_near;

in vec3 clipping_planes_dots;
in float color_clip_plane_dot;

// x = diffuse, y = specular;
in vec2 intensity;

in vec4 world_pos;
in vec3 world_normal;
in float world_normal_z;
in vec3 eye_normal;

vec3 getBackfaceColor(vec3 fill) {
    float brightness = 0.2126 * fill.r + 0.7152 * fill.g + 0.0722 * fill.b;
    return (brightness > 0.75) ? vec3(0.11, 0.165, 0.208) : vec3(0.988, 0.988, 0.988);
}

// Silhouette edge detection & rendering algorithem by leoneruggiero
// https://www.shadertoy.com/view/DslXz2
#define INFLATE 1

float GetTolerance(float d, float k)
{
    // -------------------------------------------
    // Find a tolerance for depth that is constant
    // in view space (k in view space).
    //
    // tol = k*ddx(ZtoDepth(z))
    // -------------------------------------------
    
    float A=-   (z_far+z_near)/(z_far-z_near);
    float B=-2.0*z_far*z_near /(z_far-z_near);
    
    d = d*2.0-1.0;
    
    return -k*(d+A)*(d+A)/B;   
}

float DetectSilho(vec2 fragCoord, vec2 dir)
{
    // -------------------------------------------
    //   x0 ___ x1----o 
    //          :\    : 
    //       r0 : \   : r1
    //          :  \  : 
    //          o---x2 ___ x3
    //
    // r0 and r1 are the differences between actual
    // and expected (as if x0..3 where on the same
    // plane) depth values.
    // -------------------------------------------
    
    float x0 = abs(texture(depth_tex, (fragCoord + dir*-2.0) / screen_size).r);
    float x1 = abs(texture(depth_tex, (fragCoord + dir*-1.0) / screen_size).r);
    float x2 = abs(texture(depth_tex, (fragCoord + dir* 0.0) / screen_size).r);
    float x3 = abs(texture(depth_tex, (fragCoord + dir* 1.0) / screen_size).r);
    
    float d0 = (x1-x0);
    float d1 = (x2-x3);
    
    float r0 = x1 + d0 - x2;
    float r1 = x2 + d1 - x1;
    
    float tol = GetTolerance(x2, 0.04);
    
    return smoothstep(0.0, tol*tol, max( - r0*r1, 0.0));

}

float DetectSilho(vec2 fragCoord)
{
    return max(
        DetectSilho(fragCoord, vec2(1,0)), // Horizontal
        DetectSilho(fragCoord, vec2(0,1))  // Vertical
        );
}

vec3 strengthLensColor(float reserve)
{
    reserve = clamp(reserve, 0.0, 1.0);
    vec3 red = vec3(0.86, 0.10, 0.08);
    vec3 orange = vec3(0.96, 0.48, 0.10);
    vec3 yellow = vec3(0.96, 0.86, 0.16);
    vec3 green = vec3(0.20, 0.78, 0.35);
    vec3 blue = vec3(0.10, 0.42, 0.96);

    if (reserve < 0.25)
        return mix(red, orange, reserve / 0.25);
    if (reserve < 0.50)
        return mix(orange, yellow, (reserve - 0.25) / 0.25);
    if (reserve < 0.75)
        return mix(yellow, green, (reserve - 0.50) / 0.25);
    return mix(green, blue, (reserve - 0.75) / 0.25);
}

vec4 applyStrengthLens(vec4 base_color)
{
    if (!strength_lens.enabled)
        return base_color;

    vec3 axis = max(strength_lens.axis_strength, vec3(EPSILON));
    float strongest = max(max(axis.x, axis.y), axis.z);
    vec3 rel = clamp((world_pos.xyz - strength_lens.bbox_min) / max(strength_lens.bbox_size, vec3(EPSILON)), 0.0, 1.0);
    vec3 normal_abs = abs(normalize(world_normal));
    vec3 load_axis = normalize(strength_lens.load_axis);
    vec3 weak_axis = normalize(strength_lens.weak_axis);

    float directional_reserve = clamp(dot(normal_abs, axis) / strongest, 0.0, 1.0);
    float orientation_reserve = clamp(dot(abs(load_axis), axis) / strongest, 0.0, 1.0);
    float load_span = abs(dot(rel - vec3(0.5), load_axis)) * 2.0;
    float edge_span = max(max(abs(rel.x - 0.5), abs(rel.y - 0.5)), abs(rel.z - 0.5)) * 2.0;
    float span_concern = clamp(0.55 * load_span + 0.45 * edge_span, 0.0, 1.0);
    float layer_penalty = (1.0 - axis.z / strongest) * pow(abs(dot(normalize(world_normal), weak_axis)), 1.5);

    float reserve = mix(orientation_reserve, directional_reserve, 0.45);
    reserve -= strength_lens.surface_weight * (1.0 - directional_reserve);
    reserve -= strength_lens.load_span_weight * span_concern * (1.0 - orientation_reserve);
    reserve -= strength_lens.layer_penalty_weight * layer_penalty;
    reserve = clamp((reserve - 0.10) / 0.82, 0.0, 1.0);

    vec3 heat = strengthLensColor(reserve);
    base_color.rgb = mix(base_color.rgb, heat, 0.88);
    base_color.a = max(base_color.a, 0.92);
    return base_color;
}

out vec4 out_color;

void main()
{
    if (any(lessThan(clipping_planes_dots, ZERO)))
        discard;

    vec4 color;
	if (use_color_clip_plane) {
		color.rgb = (color_clip_plane_dot < 0.0) ? uniform_color_clip_plane_1.rgb : uniform_color_clip_plane_2.rgb;
		color.a = uniform_color.a;
    }
    else
	    color = uniform_color;

    if (slope.actived) {
         if(world_pos.z<0.1&&world_pos.z>-0.1)
         {
                color.rgb = LightBlue;
                color.a = 0.8;
         }
         else if( world_normal_z < slope.normal_z - EPSILON)
         {
                color.rgb = color.rgb * 0.5 + LightRed * 0.5;
                color.a = 0.8;
         }
    }
    color = applyStrengthLens(color);

    // if the fragment is outside the print volume -> use darker color
	vec3 pv_check_min = ZERO;
	vec3 pv_check_max = ZERO;
    if (print_volume.type == 0) {
		// rectangle
		pv_check_min = world_pos.xyz - vec3(print_volume.xy_data.x, print_volume.xy_data.y, print_volume.z_data.x);
		pv_check_max = world_pos.xyz - vec3(print_volume.xy_data.z, print_volume.xy_data.w, print_volume.z_data.y);
	}
	else if (print_volume.type == 1) {
		// circle
		float delta_radius = print_volume.xy_data.z - distance(world_pos.xy, print_volume.xy_data.xy);
		pv_check_min = vec3(delta_radius, 0.0, world_pos.z - print_volume.z_data.x);
		pv_check_max = vec3(0.0, 0.0, world_pos.z - print_volume.z_data.y);
	}
	color.rgb = (any(lessThan(pv_check_min, ZERO)) || any(greaterThan(pv_check_max, ZERO))) ? mix(color.rgb, ZERO, 0.3333) : color.rgb;

    //BBS: add outline_color
    if (is_outline) {
        color = vec4(vec3(intensity.y) + color.rgb * intensity.x, color.a);
        vec2 fragCoord = gl_FragCoord.xy;
        float s = DetectSilho(fragCoord);
        // Makes silhouettes thicker.
        for(int i=1;i<=INFLATE; i++)
        {
           s = max(s, DetectSilho(fragCoord.xy + vec2(i, 0)));
           s = max(s, DetectSilho(fragCoord.xy + vec2(0, i)));
        }   
        out_color = vec4(mix(color.rgb, getBackfaceColor(color.rgb), s), color.a);
    }
#ifdef ENABLE_ENVIRONMENT_MAP
    else if (use_environment_tex)
        out_color = vec4(0.45 * texture(environment_tex, normalize(eye_normal).xy * 0.5 + 0.5).xyz + 0.8 * color.rgb * intensity.x, color.a);
#endif
    else
        out_color = vec4(vec3(intensity.y) + color.rgb * intensity.x, color.a);
}
