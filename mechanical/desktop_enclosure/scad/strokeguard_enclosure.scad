part = is_undef(part) ? "assembled" : part;
variant = is_undef(variant) ? "printable" : variant;

include <parameters.scad>
include <parts.scad>

if (part == "compact_shell") compact_shell();
else if (part == "front_panel") front_panel();
else if (part == "electronics_tray") electronics_tray();
else if (part == "rear_cover") rear_cover();
else if (part == "desktop_base") desktop_base();
else if (part == "assembled") assembled_view();
else if (part == "exploded") exploded_view();
else if (part == "display_stl") display_stl_model();
else assert(false, str("Unknown part: ", part));
