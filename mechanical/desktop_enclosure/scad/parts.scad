module rounded_xy_box(size, radius = 3) {
    linear_extrude(height = size[2])
        offset(r = radius)
            square([size[0] - 2 * radius, size[1] - 2 * radius], center = true);
}

module rounded_plate(width, height, thickness, radius = 2) {
    linear_extrude(height = thickness)
        offset(r = radius)
            square([width - 2 * radius, height - 2 * radius], center = true);
}

module linear_slot(length, diameter, height, axis = "x") {
    hull() {
        for (offset = [-length / 2, length / 2])
            if (axis == "x")
                translate([offset, 0, 0]) cylinder(h = height, d = diameter);
            else
                translate([0, offset, 0]) cylinder(h = height, d = diameter);
    }
}

module shell_frame() {
    difference() {
        rounded_xy_box([body_width, body_depth, body_height], corner_radius);
        translate([0, 0, body_height / 2])
            cube([
                body_width - 2 * wall,
                body_depth + 2 * epsilon,
                body_height - 2 * wall
            ], center = true);
    }
}

module front_panel_rails() {
    rail_x = front_panel_width / 2 - 0.5;
    rail_y = -body_depth / 2 + wall + panel_slot_depth / 2;

    for (x = [-rail_x, rail_x])
        translate([x, rail_y, body_height / 2])
            cube([3, panel_slot_depth, front_panel_height], center = true);
}

module rear_cover_bosses() {
    for (x = rear_cover_fastener_x, z_offset = rear_cover_fastener_z)
        let(
            side = x < 0 ? -1 : 1,
            support_width = body_width / 2 - wall - abs(x) + 2,
            support_x = side * (abs(x) + body_width / 2 - wall) / 2,
            boss_z = body_height / 2 + z_offset
        )
            difference() {
                union() {
                    translate([x, body_depth / 2 - wall, boss_z])
                        rotate([90, 0, 0])
                            cylinder(h = 6, d = rear_cover_boss_diameter, center = true);
                    translate([support_x, body_depth / 2 - wall, boss_z])
                        cube([
                            support_width,
                            6,
                            rear_cover_boss_diameter
                        ], center = true);
                }

                translate([x, body_depth / 2 - wall, boss_z])
                    rotate([90, 0, 0])
                        cylinder(h = 6 + 2 * epsilon, d = m3_clearance, center = true);
            }
}

module compact_shell_model() {
    difference() {
        union() {
            shell_frame();
            front_panel_rails();
            rear_cover_bosses();
        }

        for (x = base_fastener_x)
            translate([x, 0, -epsilon])
                cylinder(h = wall + 2 * epsilon, d = m3_clearance);
    }
}

module compact_shell() {
    translate([0, 0, body_width / 2])
        rotate([0, 90, 0]) compact_shell_model();
}

module front_panel() {
    difference() {
        rounded_plate(
            front_panel_width,
            front_panel_height,
            front_panel_thickness,
            3
        );

        translate([0, camera_position_z - body_height / 2, -epsilon])
            cylinder(
                h = front_panel_thickness + 2 * epsilon,
                d = camera_aperture_diameter
            );

        translate([0, -front_panel_height / 2, -epsilon])
            cube([8, 4, front_panel_thickness + 2 * epsilon], center = true);
    }
}

module rear_cover() {
    cover_width = body_width - 2 * rear_opening_margin + 8;
    cover_height = body_height - 2 * rear_opening_margin + 8;

    difference() {
        rounded_plate(cover_width, cover_height, rear_cover_thickness, 3);

        for (x = rear_cover_fastener_x, z_offset = rear_cover_fastener_z)
            translate([x, z_offset, -epsilon])
                cylinder(h = rear_cover_thickness + 2 * epsilon, d = m3_clearance);

        for (y = [-45, -30, -15, 0, 15, 30, 45])
            translate([0, y, -epsilon])
                cube([60, 3, rear_cover_thickness + 2 * epsilon], center = true);

        translate([0, -cover_height / 2, -epsilon])
            cube([18, 8, rear_cover_thickness + 2 * epsilon], center = true);
    }
}

module desktop_base() {
    slot_cutter_height = 20;
    difference() {
        rounded_xy_box([base_width, base_depth, base_height], 6);

        translate([0, 0, base_height + 4])
            rotate([-lean_angle, 0, 0])
                cube([
                    body_width + moving_clearance,
                    body_depth + moving_clearance,
                    slot_cutter_height
                ], center = true);

        for (x = base_fastener_x)
            translate([x, 0, -epsilon])
                cylinder(h = base_height + 2 * epsilon, d = m3_clearance);
    }
}

module camera_clamp() {
    clamp_inner = [
        camera_board[0] + 2 * camera_clearance,
        camera_board[1] + 2 * camera_clearance,
        camera_board[2]
    ];
    plate_width = clamp_inner[0] + 10;
    plate_height = clamp_inner[1] + 6;
    guide_thickness = 2.4;

    difference() {
        rounded_plate(plate_width, plate_height, service_part_thickness, 3);
        translate([0, 0, -epsilon])
            cube([
                camera_board[0] - 8,
                camera_board[1] - 8,
                service_part_thickness + 2 * epsilon
            ], center = true);

        for (x = [-plate_width / 2 + 4, plate_width / 2 - 4])
            translate([x, 0, -epsilon])
                cube([3, 22, service_part_thickness + 2 * epsilon], center = true);
    }

    for (x = [
        -clamp_inner[0] / 2 - guide_thickness / 2,
        clamp_inner[0] / 2 + guide_thickness / 2
    ])
        translate([x, 0, service_part_thickness + clamp_inner[2] / 2])
            cube([guide_thickness, clamp_inner[1], clamp_inner[2]], center = true);

    for (y = [-clamp_inner[1] / 2, clamp_inner[1] / 2])
        translate([0, y, service_part_thickness + 3])
            cube([clamp_inner[0], guide_thickness, 6], center = true);
}

module controller_rail() {
    rail_size = [controller_rail_length, 16, 5];
    difference() {
        rounded_xy_box(rail_size, 2);

        for (x = [-32, -16, 0, 16, 32])
            translate([x, 0, -epsilon])
                linear_slot(8, m3_clearance, rail_size[2] + 2 * epsilon, "x");

        for (x = [-41, 41])
            translate([x, 0, -epsilon])
                cube([3, 10, rail_size[2] + 2 * epsilon], center = true);
    }
}

module microphone_holder() {
    holder_size = [30, 24, 4];
    difference() {
        rounded_xy_box(holder_size, 3);
        translate([0, 0, -epsilon])
            cylinder(h = holder_size[2] + 2 * epsilon, d = 8);
        for (x = [-9, 9])
            translate([x, 0, -epsilon])
                cube([3, 16, holder_size[2] + 2 * epsilon], center = true);
        translate([0, 10, -epsilon])
            cube([8, 8, holder_size[2] + 2 * epsilon], center = true);
    }

    for (x = [-13, 13])
        translate([x, 0, 8])
            cube([2, 18, 12], center = true);
}

module installed_front_and_rear() {
    translate([0, -body_depth / 2 + front_panel_thickness, body_height / 2])
        rotate([90, 0, 0]) front_panel();
    translate([0, body_depth / 2 + rear_cover_thickness, body_height / 2])
        rotate([90, 0, 0]) rear_cover();
}

module installed_service_parts() {
    clamp_height = camera_board[1] + 2 * camera_clearance + 6;
    clamp_center_z = min(
        camera_position_z,
        body_height - wall - clamp_height / 2
    );

    color([0.30, 0.35, 0.37])
        translate([0, -body_depth / 2 + wall + front_panel_thickness, clamp_center_z])
            rotate([-90, 0, 0]) camera_clamp();

    color([0.25, 0.30, 0.32])
        translate([0, body_depth / 2 - 6, 78])
            rotate([90, 0, 0]) controller_rail();

    color([0.25, 0.30, 0.32])
        translate([0, -5, 12]) microphone_holder();
}

module assembled_body(include_service_parts = true) {
    compact_shell_model();
    installed_front_and_rear();
    if (include_service_parts) installed_service_parts();
}

module assembled_view() {
    color([0.10, 0.13, 0.15]) desktop_base();
    color([0.14, 0.17, 0.19])
        translate([0, 0, base_height - 4])
            rotate([-lean_angle, 0, 0]) assembled_body();
}

module display_body_solid() {
    difference() {
        rounded_xy_box([body_width, body_depth, body_height], corner_radius);
        translate([0, 0, camera_position_z])
            rotate([90, 0, 0])
                cylinder(
                    h = body_depth + 2 * epsilon,
                    d = camera_aperture_diameter,
                    center = true
                );
    }
}

module display_stl_model() {
    union() {
        rounded_xy_box([base_width, base_depth, base_height], 6);
        translate([0, 0, base_height - 6])
            rotate([-lean_angle, 0, 0]) display_body_solid();
    }
}

module exploded_view() {
    color([0.14, 0.17, 0.19]) translate([0, 0, 20]) compact_shell_model();
    color([0.18, 0.21, 0.23])
        translate([-85, -35, 102]) rotate([90, 0, 0]) front_panel();
    color([0.34, 0.38, 0.40])
        translate([85, 35, 102]) rotate([90, 0, 0]) rear_cover();
    color([0.10, 0.13, 0.15]) translate([0, 0, -30]) desktop_base();
    color([0.30, 0.35, 0.37]) translate([-55, -45, 135]) camera_clamp();
    color([0.25, 0.30, 0.32]) translate([55, -45, 75]) controller_rail();
    color([0.25, 0.30, 0.32]) translate([0, -45, 20]) microphone_holder();
}
