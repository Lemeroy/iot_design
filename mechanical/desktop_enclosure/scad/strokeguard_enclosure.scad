part = is_undef(part) ? "assembled" : part;
variant = is_undef(variant) ? "printable" : variant;
panel_thickness = is_undef(panel_thickness) ? 2 : panel_thickness;

include <parameters.scad>
include <parts.scad>

if (part == "upper_shell") upper_shell();
else if (part == "lower_shell") lower_shell();
else if (part == "upper_rear_cover") upper_rear_cover();
else if (part == "lower_rear_cover") lower_rear_cover();
else if (part == "base") base();
else if (part == "lean_support") lean_support();
else if (part == "camera_carriage") camera_carriage();
else if (part == "camera_bezel") camera_bezel();
else if (part == "controller_rail") controller_rail();
else if (part == "microphone_holder") microphone_holder();
else if (part == "usb_blank") usb_blank();
else if (part == "fit_coupon") fit_coupon();
else if (part == "assembled") assembled_view();
else if (part == "exploded") exploded_view();
else if (part == "display_stl") assembled_view();
else assert(false, str("Unknown part: ", part));
