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
                        cylinder(h = 6 + 2 * epsilon, d = m3_pilot_diameter, center = true);
            }
}

module tray_stop_pads() {
    stop_x = tray_width / 2 + 1;
    stop_y = tray_installed_y - tray_thickness - moving_clearance - 2;
    stop_z = tray_height / 2 - 8;

    for (x = [-stop_x, stop_x], z_offset = [-stop_z, stop_z])
        translate([x, stop_y, body_height / 2 + z_offset])
            cube([8, 4, 10], center = true);
}

module base_pilot_bosses() {
    for (x = base_fastener_x)
        translate([x, 0, 0]) cylinder(h = 8, d = 9);
}

module compact_shell_model() {
    difference() {
        union() {
            shell_frame();
            front_panel_rails();
            rear_cover_bosses();
            tray_stop_pads();
            base_pilot_bosses();
        }

        for (x = base_fastener_x)
            translate([x, 0, -epsilon])
                cylinder(h = 8 + 2 * epsilon, d = m3_pilot_diameter);
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

module rear_cover_pressure_posts() {
    post_start_z = rear_cover_thickness - tray_stop_overlap;
    post_height = body_depth / 2 - 2 * rear_cover_thickness
        - tray_installed_y - rear_cover_post_gap + tray_stop_overlap;
    post_z = post_start_z + post_height / 2;

    for (x = [-42, 42], y = [-60, 60])
        translate([x, y, post_z]) cube([8, 8, post_height], center = true);
}

module rear_cover() {
    cover_width = body_width - 2 * rear_opening_margin + 8;
    cover_height = body_height - 2 * rear_opening_margin + 8;

    union() {
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
        rear_cover_pressure_posts();
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
            translate([x, 0, base_height / 2])
                rotate([-lean_angle, 0, 0])
                    cylinder(
                        h = base_height + 4,
                        d = m3_clearance,
                        center = true
                    );
    }
}

module electronics_tray() {
    camera_inner = [
        camera_mount_inner_width,
        camera_board[1] + 2 * camera_clearance
    ];
    camera_y = tray_height / 2 - camera_board[1] / 2 - 3;
    microphone_y = -tray_height / 2 + 15;
    guide_thickness = 2.4;
    feature_z = tray_thickness - tray_stop_overlap + tray_feature_height / 2;

    difference() {
        union() {
            rounded_plate(tray_width, tray_height, tray_thickness, 3);

            for (x = [
                -camera_inner[0] / 2 - guide_thickness / 2,
                camera_inner[0] / 2 + guide_thickness / 2
            ])
                translate([x, camera_y, feature_z])
                    cube([
                        guide_thickness,
                        camera_inner[1],
                        tray_feature_height
                    ], center = true);

            for (y = [
                camera_y - camera_inner[1] / 2 - guide_thickness / 2,
                camera_y + camera_inner[1] / 2 + guide_thickness / 2
            ])
                translate([0, y, tray_thickness - tray_stop_overlap + 3])
                    cube([
                        camera_inner[0] + 2 * guide_thickness,
                        guide_thickness,
                        6
                    ], center = true);

            for (x = [-13, 13])
                translate([x, microphone_y, tray_thickness - tray_stop_overlap + 4])
                    cube([2, 18, 8], center = true);
        }

        translate([0, camera_y, (tray_thickness + tray_feature_height) / 2])
            cube([
                camera_board[0] - 8,
                camera_board[1] - 8,
                tray_thickness + tray_feature_height + 2 * epsilon
            ], center = true);

        for (x = [-20, 20])
            translate([x, camera_y, tray_thickness / 2])
                cube([3, 28, tray_thickness + 2 * epsilon], center = true);

        for (x = [-30, -10, 10, 30], y = [-25, -5, 15])
            translate([x, y, tray_thickness / 2])
                cube([3, 12, tray_thickness + 2 * epsilon], center = true);

        for (x = [-10, 10])
            translate([x, microphone_y, tray_thickness / 2])
                cube([3, 16, tray_thickness + 2 * epsilon], center = true);

        translate([0, microphone_y, -epsilon])
            cylinder(h = tray_thickness + tray_feature_height + 2 * epsilon, d = 8);

        for (y = [-42, 24])
            translate([0, y, tray_thickness / 2])
                cube([18, 4, tray_thickness + 2 * epsilon], center = true);
    }
}

module installed_front_and_rear() {
    translate([0, -body_depth / 2 + front_panel_thickness, body_height / 2])
        rotate([90, 0, 0]) front_panel();
    translate([0, body_depth / 2 + rear_cover_thickness, body_height / 2])
        rotate([90, 0, 0]) rear_cover();
}

module installed_electronics_tray() {
    color([0.30, 0.35, 0.37])
        translate([0, tray_installed_y, body_height / 2])
            rotate([90, 0, 0]) electronics_tray();
}

module assembled_body(include_service_parts = true) {
    compact_shell_model();
    installed_front_and_rear();
    if (include_service_parts) installed_electronics_tray();
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
    color([0.30, 0.35, 0.37]) translate([0, -55, 75]) electronics_tray();
}
