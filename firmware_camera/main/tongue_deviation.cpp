#include "tongue_deviation.h"

#include <algorithm>
#include <cmath>
#include <cstring>

namespace {

constexpr int kMaxRoiWidth = 160;
constexpr int kMaxRoiHeight = 120;
constexpr int kMaxPixels = kMaxRoiWidth * kMaxRoiHeight;
constexpr float kPi = 3.14159265358979323846f;
constexpr int kMinTongueSaturation = 25;
constexpr int kMinRedGreenDelta = 20;
constexpr int kMinRedBlueDelta = 15;

uint8_t s_visited[(kMaxPixels + 7) / 8];
uint16_t s_queue[kMaxPixels];

struct Component {
    int area;
    int64_t sum_x;
    int64_t sum_y;
    int saturation_sum;
    int min_x;
    int max_x;
    int min_y;
    int max_y;
    bool touches_border;
};

bool visited(int index)
{
    return (s_visited[index >> 3] & (1U << (index & 7))) != 0;
}

void mark_visited(int index)
{
    s_visited[index >> 3] |= (uint8_t)(1U << (index & 7));
}

bool tongue_pixel(const sg_tongue_input_t &input, int local_x, int local_y,
                  int *saturation_out = nullptr)
{
    const int x = input.roi.x + local_x;
    const int y = input.roi.y + local_y;
    const uint8_t *pixel = input.rgb888 + y * input.stride_bytes + x * 3;
    const int red = pixel[0];
    const int green = pixel[1];
    const int blue = pixel[2];
    const int saturation = std::max({red, green, blue})
                         - std::min({red, green, blue});
    if (saturation_out != nullptr) *saturation_out = saturation;
    return red >= 70 && saturation >= kMinTongueSaturation
        && red >= green + kMinRedGreenDelta
        && red >= blue + kMinRedBlueDelta;
}

Component collect_component(const sg_tongue_input_t &input, int start)
{
    Component component = {
        .area = 0,
        .sum_x = 0,
        .sum_y = 0,
        .saturation_sum = 0,
        .min_x = kMaxRoiWidth,
        .max_x = 0,
        .min_y = kMaxRoiHeight,
        .max_y = 0,
        .touches_border = false,
    };
    int head = 0;
    int tail = 0;
    s_queue[tail++] = (uint16_t)start;
    mark_visited(start);
    while (head < tail) {
        const int index = s_queue[head++];
        const int x = index % input.roi.width;
        const int y = index / input.roi.width;
        int saturation = 0;
        if (!tongue_pixel(input, x, y, &saturation)) continue;
        ++component.area;
        component.sum_x += input.roi.x + x;
        component.sum_y += input.roi.y + y;
        component.saturation_sum += saturation;
        component.min_x = std::min(component.min_x, x);
        component.max_x = std::max(component.max_x, x);
        component.min_y = std::min(component.min_y, y);
        component.max_y = std::max(component.max_y, y);
        if (x == 0 || y == 0 || x + 1 == input.roi.width
            || y + 1 == input.roi.height) {
            component.touches_border = true;
        }
        const int neighbors[4][2] = {{x - 1, y}, {x + 1, y}, {x, y - 1}, {x, y + 1}};
        for (const auto &neighbor : neighbors) {
            const int nx = neighbor[0];
            const int ny = neighbor[1];
            if (nx < 0 || ny < 0 || nx >= input.roi.width || ny >= input.roi.height) continue;
            const int next = ny * input.roi.width + nx;
            if (!visited(next) && tongue_pixel(input, nx, ny)) {
                mark_visited(next);
                s_queue[tail++] = (uint16_t)next;
            }
        }
    }
    return component;
}

bool plausible(const Component &component, int roi_area,
               const sg_tongue_input_t &input)
{
    if (component.area * 100 < roi_area / 2 || component.area * 100 > roi_area * 60
        || component.touches_border) {
        return false;
    }
    const int width = component.max_x - component.min_x + 1;
    const int height = component.max_y - component.min_y + 1;
    if (width * 100 < height * 35 || width * 100 > height * 250) {
        return false;
    }
    const int mouth_local_y = (int)input.mouth_y - input.roi.y;
    const int bottom_protrusion = component.max_y - mouth_local_y;
    const int centroid_y = (int)(component.sum_y / component.area);
    const int centroid_protrusion = centroid_y - input.mouth_y;
    return bottom_protrusion >= std::max(6, (int)input.face_width / 5)
        && centroid_protrusion >= std::max(3, (int)input.face_width / 10);
}

uint8_t score_offset(int absolute_percent)
{
    if (absolute_percent <= 5) return 100;
    if (absolute_percent >= 25) return 20;
    return (uint8_t)(100 - (absolute_percent - 5) * 4);
}

}  // namespace

extern "C" bool sg_tongue_measure(
    const sg_tongue_input_t *input, sg_tongue_measurement_t *out)
{
    if (input == nullptr || out == nullptr || input->rgb888 == nullptr
        || input->width == 0 || input->height == 0
        || input->stride_bytes < input->width * 3U || input->face_width == 0
        || input->mouth_y < input->roi.y
        || input->mouth_y >= input->roi.y + input->roi.height
        || input->roi.width == 0 || input->roi.height == 0
        || input->roi.width > kMaxRoiWidth || input->roi.height > kMaxRoiHeight
        || input->roi.x + input->roi.width > input->width
        || input->roi.y + input->roi.height > input->height
        || std::fabs(input->face_roll_deg) > 25.0f) {
        return false;
    }
    std::memset(out, 0, sizeof(*out));
    const int roi_area = input->roi.width * input->roi.height;
    std::memset(s_visited, 0, (roi_area + 7) / 8);
    Component best = {};
    for (int index = 0; index < roi_area; ++index) {
        if (visited(index)) continue;
        const int x = index % input->roi.width;
        const int y = index / input->roi.width;
        if (!tongue_pixel(*input, x, y)) {
            mark_visited(index);
            continue;
        }
        const Component candidate = collect_component(*input, index);
        if (plausible(candidate, roi_area, *input) && candidate.area > best.area) best = candidate;
    }
    if (best.area == 0) return false;

    const float centroid_x = (float)best.sum_x / best.area;
    const float centroid_y = (float)best.sum_y / best.area;
    const float radians = input->face_roll_deg * kPi / 180.0f;
    const float local_x = (centroid_x - input->axis_origin.x) * std::cos(radians)
                        + (centroid_y - input->axis_origin.y) * std::sin(radians);
    const int signed_percent = (int)std::lround(local_x * 100.0f / input->face_width);
    const int bounded_percent = std::clamp(signed_percent, -100, 100);
    const int area_quality = std::clamp(best.area * 500 / roi_area, 0, 100);
    const int saturation_quality = std::clamp(
        (best.saturation_sum / best.area - kMinTongueSaturation)
            * 100 / 115,
        0, 100);
    out->signed_offset = (int8_t)bounded_percent;
    out->score = score_offset(std::abs(bounded_percent));
    out->quality = (uint8_t)std::min(area_quality, saturation_quality);
    return true;
}
