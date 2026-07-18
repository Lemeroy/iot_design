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

module front_panel(section_height, camera = false) {
    difference() {
        translate([0, -body_depth / 2 - panel_thickness / 2, section_height / 2])
            cube([body_width - 2 * wall, panel_thickness, section_height - 2 * wall], center = true);

        if (camera)
            translate([0, -body_depth / 2 - panel_thickness / 2, section_height - 24])
                cube([camera_window[0], panel_thickness + 2 * epsilon, camera_window[1]], center = true);
    }
}

module front_panel_skin_plate(panel_height) {
    translate([-front_panel_width / 2, 0, -front_panel_skin])
        cube([front_panel_width, panel_height, front_panel_skin]);
}

module front_panel_rear_rib(x, y, width, height) {
    translate([
        x - width / 2,
        y - height / 2,
        -front_panel_skin - front_panel_rib_height
    ])
        cube([
            width,
            height,
            front_panel_rib_height + epsilon
        ]);
}

module front_panel_lower_printable() {
    usable_width = front_panel_width - 2 * front_panel_rail_keepout;
    rib_height = front_panel_half_height - 38;

    union() {
        front_panel_skin_plate(front_panel_half_height);

        for (x = [-62, 62])
            front_panel_rear_rib(x, 20 + rib_height / 2, front_panel_rib_width, rib_height);
        for (y = [45, 100])
            front_panel_rear_rib(0, y, usable_width, front_panel_rib_width);

        translate([
            -usable_width / 2,
            front_panel_half_height - epsilon,
            -front_panel_skin - 1.2
        ])
            cube([
                usable_width,
                front_panel_lap_height + epsilon,
                1.2 + epsilon
            ]);
    }
}

module front_panel_upper_printable() {
    usable_width = front_panel_width - 2 * front_panel_rail_keepout;
    camera_local_y = body_height - 24 - (wall + front_panel_half_height + front_panel_gap);
    rib_height = front_panel_half_height - 28;

    difference() {
        union() {
            front_panel_skin_plate(front_panel_half_height);

            for (x = [-62, 62])
                front_panel_rear_rib(x, 14 + rib_height / 2, front_panel_rib_width, rib_height);
            for (y = [40, 80])
                front_panel_rear_rib(0, y, usable_width, front_panel_rib_width);
        }

        translate([
            -camera_window[0] / 2,
            camera_local_y - camera_window[1] / 2,
            -front_panel_skin - front_panel_rib_height - epsilon
        ])
            cube([
                camera_window[0],
                camera_window[1],
                front_panel_skin + front_panel_rib_height + 2 * epsilon
            ]);
    }
}

module front_panel_assembled() {
    translate([0, -body_depth / 2, wall])
        rotate([90, 0, 0])
            front_panel_lower_printable();
    translate([
        0,
        -body_depth / 2,
        wall + front_panel_half_height + front_panel_gap
    ])
        rotate([90, 0, 0])
            front_panel_upper_printable();
}

module panel_retaining_rails(section_height, top_closed = false, bottom_closed = false) {
    panel_slot = panel_thickness + panel_clearance;
    rail_y = -body_depth / 2 + wall + panel_slot + 1;
    rail_x = body_width / 2 - wall - panel_slot - 1;

    for (side = [-1, 1])
        translate([side * rail_x, rail_y, section_height / 2])
            cube([2, panel_slot_depth, section_height - 2 * wall], center = true);

    if (top_closed)
        translate([0, rail_y, section_height - wall - panel_slot - 1])
            cube([body_width - 2 * wall, panel_slot_depth, 2], center = true);

    if (bottom_closed)
        translate([0, rail_y, wall + panel_slot + 1])
            cube([body_width - 2 * wall, panel_slot_depth, 2], center = true);
}

module rear_service_opening(section_height) {
    translate([0, body_depth / 2 - wall / 2, section_height / 2])
        cube([
            body_width - 2 * rear_opening_margin,
            wall + 2 * epsilon,
            section_height - 2 * rear_opening_margin
        ], center = true);
}

module side_usb_windows(section_height) {
    for (side = [-1, 1])
        translate([side * body_width / 2, -2, section_height * 0.48])
            cube([wall + 2 * epsilon, 30, 16], center = true);
}

module rear_cover_bosses(section_height) {
    boss_y = body_depth / 2 - 4;
    for (x = rear_cover_fastener_x, z = rear_cover_fastener_z)
        difference() {
            translate([x, boss_y, section_height / 2 + z])
                rotate([90, 0, 0])
                    cylinder(h = 8, d = rear_cover_boss_diameter, center = true);
            translate([x, boss_y, section_height / 2 + z])
                rotate([90, 0, 0])
                    cylinder(h = 8 + 2 * epsilon, d = m3_clearance, center = true);
        }
}

module shell_section(section_height, top_closed = false, bottom_closed = false, usb_windows = true) {
    inner_z0 = bottom_closed ? wall : -epsilon;
    inner_z1 = top_closed ? section_height - wall : section_height + epsilon;

    union() {
        difference() {
            rounded_xy_box([body_width, body_depth, section_height], corner_radius);

            translate([0, -wall / 2, (inner_z0 + inner_z1) / 2])
                cube([
                    body_width - 2 * wall,
                    body_depth - wall + 2 * epsilon,
                    inner_z1 - inner_z0
                ], center = true);

            rear_service_opening(section_height);

            if (usb_windows)
                side_usb_windows(section_height);
        }

        panel_retaining_rails(section_height, top_closed, bottom_closed);
        rear_cover_bosses(section_height);
    }
}

module joint_tongue() {
    difference() {
        translate([0, -wall / 2, split_height + tongue_overlap / 2])
            cube([
                body_width - 2 * (wall + tongue_clearance),
                body_depth - wall - 2 * tongue_clearance,
                tongue_overlap
            ], center = true);

        translate([0, -wall, split_height + tongue_overlap / 2])
            cube([
                body_width - 2 * (wall + tongue_clearance + joint_lip),
                body_depth - wall - 2 * (tongue_clearance + joint_lip),
                tongue_overlap + 2 * epsilon
            ], center = true);

        translate([0, -body_depth / 2, split_height + tongue_overlap / 2])
            cube([body_width, wall * 3, tongue_overlap + 2 * epsilon], center = true);
    }
}

module joint_bosses(z_offset = 0) {
    for (x = joint_fastener_x)
        difference() {
            translate([x, body_depth / 2 - 8, z_offset])
                cylinder(h = 8, d = 9, center = true);
            translate([x, body_depth / 2 - 8, z_offset])
                cylinder(h = 8 + 2 * epsilon, d = m3_clearance, center = true);
        }
}

module upper_shell() {
    translate([0, 0, -split_height])
        union() {
            translate([0, 0, split_height])
                shell_section(split_height, top_closed = true, bottom_closed = false, usb_windows = true);
            joint_bosses(split_height + 4);
        }
}

module lower_shell() {
    union() {
        shell_section(split_height, top_closed = false, bottom_closed = true, usb_windows = true);
        joint_tongue();
        joint_bosses(split_height - 4);
    }
}

module rear_cover(section_height = split_height, lower = false) {
    difference() {
        rounded_plate(
            body_width - 2 * rear_opening_margin + 8,
            section_height - 2 * rear_opening_margin + 8,
            rear_cover_thickness,
            3
        );

        for (x = rear_cover_fastener_x, z = rear_cover_fastener_z)
            translate([x, z, -epsilon])
                cylinder(h = rear_cover_thickness + 2 * epsilon, d = m3_clearance);

        if (lower)
            for (z = [-40, -24, -8, 8, 24, 40])
                translate([0, z, -epsilon])
                    cube([92, 4, rear_cover_thickness + 2 * epsilon], center = true);
    }
}

module upper_rear_cover() {
    rear_cover(lower = false);
}

module lower_rear_cover() {
    rear_cover(lower = true);
}

module base() {
    support_width = 96;
    support_depth = 42;
    difference() {
        rounded_xy_box([body_width, base_depth, base_height], 7);
        translate([0, support_mount_offset_y + support_depth / 2, base_height - 4])
            cube([support_width + moving_clearance, support_depth + moving_clearance, 8 + epsilon], center = true);
        for (x = base_support_fastener_x)
            translate([x, base_support_fastener_y, -epsilon])
                cylinder(h = base_height + 2 * epsilon, d = m3_clearance);
    }
}

module lean_support_solid() {
    support_width = 96;
    support_depth = 42;
    support_height = 82;
    top_offset = tan(lean_angle) * support_height;

    rotate([90, 0, 90])
        linear_extrude(height = support_width, center = true)
            polygon(points = [
                [0, 0],
                [support_depth, 0],
                [support_depth - top_offset, support_height],
                [support_depth - top_offset - 8, support_height]
            ]);
}

module lean_support() {
    difference() {
        lean_support_solid();
        for (x = base_support_fastener_x)
            translate([x, base_support_fastener_y - support_mount_offset_y, -epsilon])
                cylinder(h = 12, d = m3_clearance);
    }
}

module fit_coupon() {
    difference() {
        union() {
            cube([70, 24, 8]);
            translate([4, 4, 8])
                cube([28, 16, tongue_overlap]);
            translate([40, 4, 8])
                cube([26, 16, 6]);
        }

        translate([40 + wall, 3.8, 8 + wall])
            cube([20, panel_thickness + panel_clearance, 6 + epsilon]);
        translate([57, 12, -epsilon])
            cylinder(h = 8 + 2 * epsilon, d = m3_clearance);
    }
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

module camera_carriage() {
    carriage_size = [72, 48, service_part_thickness];
    difference() {
        rounded_xy_box(carriage_size, 4);
        translate([0, 0, -epsilon])
            cube([camera_window[0] - 4, camera_window[1] - 4, service_part_thickness + 2 * epsilon], center = true);

        for (y = [-17, 17])
            translate([0, y, -epsilon])
                linear_slot(camera_adjustment, m3_clearance, service_part_thickness + 2 * epsilon, "x");
        for (x = [-28, 28])
            translate([x, 0, -epsilon])
                linear_slot(camera_adjustment, m3_clearance, service_part_thickness + 2 * epsilon, "y");
    }
}

module camera_bezel(aperture = [28, 16]) {
    bezel_size = [camera_window[0] + 8, camera_window[1] + 8, 2.4];
    difference() {
        rounded_xy_box(bezel_size, 3);
        translate([0, 0, -epsilon])
            cube([aperture[0], aperture[1], bezel_size[2] + 2 * epsilon], center = true);
    }
}

module camera_lens_placeholder() {
    rotate([90, 0, 0])
        cylinder(h = 3, d = 12, center = true);
}

module controller_rail() {
    rail_size = [126, 18, 5];
    difference() {
        rounded_xy_box(rail_size, 2);

        for (x = [-48, -16, 16, 48])
            translate([x, 0, -epsilon])
                linear_slot(12, m3_clearance, rail_size[2] + 2 * epsilon, "x");

        for (x = [-58, 58])
            translate([x, 0, -epsilon])
                cube([4, 10, rail_size[2] + 2 * epsilon], center = true);
    }
}

module microphone_holder() {
    holder_size = [38, 28, 4];
    difference() {
        rounded_xy_box(holder_size, 3);
        translate([0, 0, -epsilon])
            cylinder(h = holder_size[2] + 2 * epsilon, d = 8);
        for (x = [-12, 12])
            translate([x, 0, -epsilon])
                cube([3.5, 18, holder_size[2] + 2 * epsilon], center = true);
        translate([0, 12, -epsilon])
            cube([10, 8, holder_size[2] + 2 * epsilon], center = true);
    }

    for (x = [-17, 17])
        translate([x, 0, 7])
            cube([2, 20, 14], center = true);
}

module usb_blank() {
    blank_size = [34 - 2 * moving_clearance, 16 - 2 * moving_clearance, 2.4];
    union() {
        rounded_xy_box(blank_size, 2);
        for (y = [-5, 5])
            translate([0, y, blank_size[2]])
                cube([blank_size[0] - 4, 1.5, 1.8], center = true);
    }
}

module installed_rear_covers() {
    translate([0, body_depth / 2 + rear_cover_thickness / 2, split_height / 2])
        rotate([90, 0, 0])
            lower_rear_cover();
    translate([0, body_depth / 2 + rear_cover_thickness / 2, split_height * 1.5])
        rotate([90, 0, 0])
            upper_rear_cover();
}

module installed_service_parts() {
    camera_z = body_height - 24;

    color([0.18, 0.22, 0.24])
        translate([0, -body_depth / 2 + 8, camera_z])
            rotate([90, 0, 0]) camera_carriage();
    color([0.34, 0.39, 0.41])
        translate([0, -body_depth / 2 - panel_thickness - 1.2, camera_z])
            rotate([90, 0, 0]) camera_bezel();
    color([0.04, 0.30, 0.38])
        translate([0, -body_depth / 2 - panel_thickness - 3.2, camera_z])
            camera_lens_placeholder();

    for (z = [62, 116])
        color([0.26, 0.30, 0.32])
            translate([0, body_depth / 2 - 7, z])
                rotate([90, 0, 0]) controller_rail();

    color([0.26, 0.30, 0.32])
        translate([0, -8, 7]) microphone_holder();

    for (side = [-1, 1])
        color([0.20, 0.24, 0.26])
            translate([side * (body_width / 2 + 1.2), -2, split_height * 0.48])
                rotate([0, side * 90, 0]) usb_blank();
}

module assembled_body() {
    lower_shell();
    translate([0, 0, split_height]) upper_shell();
    front_panel_assembled();
    installed_rear_covers();
    installed_service_parts();
}

module assembled_view() {
    color([0.12, 0.15, 0.17])
        translate([0, 6, base_height])
            rotate([-lean_angle, 0, 0])
                assembled_body();
    color([0.10, 0.12, 0.13]) base();
    color([0.28, 0.32, 0.34]) translate([0, support_mount_offset_y, base_height]) lean_support();
}

module display_body_solid() {
    difference() {
        rounded_xy_box([body_width, body_depth, body_height], corner_radius);
        translate([0, -body_depth / 2, body_height - 24])
            cube([camera_window[0], body_depth + 2 * epsilon, camera_window[1]], center = true);
        for (side = [-1, 1])
            translate([side * body_width / 2, -2, split_height * 0.48])
                cube([wall + 2 * epsilon, 30, 16], center = true);
    }
}

module display_stl_model() {
    union() {
        base();
        translate([0, 6, base_height - 2])
            rotate([-lean_angle, 0, 0])
                display_body_solid();
        translate([0, support_mount_offset_y, base_height - 2]) lean_support();
    }
}

module exploded_view() {
    color([0.12, 0.15, 0.17]) translate([0, 0, 210]) upper_shell();
    color([0.16, 0.19, 0.21]) lower_shell();
    color([0.28, 0.32, 0.34]) translate([0, 95, 38]) lean_support();
    color([0.10, 0.12, 0.13]) translate([0, 0, -55]) base();
    color([0.38, 0.42, 0.44]) translate([-125, 0, 90]) upper_rear_cover();
    color([0.38, 0.42, 0.44]) translate([125, 0, 90]) lower_rear_cover();
    color([0.34, 0.39, 0.41]) translate([-105, -70, 235]) camera_carriage();
    color([0.44, 0.49, 0.51]) translate([0, -70, 235]) camera_bezel();
    color([0.28, 0.32, 0.34]) translate([-70, -70, 45]) controller_rail();
    color([0.28, 0.32, 0.34]) translate([70, -70, 45]) controller_rail();
    color([0.28, 0.32, 0.34]) translate([0, -70, 0]) microphone_holder();
    color([0.22, 0.26, 0.28]) translate([-60, -70, -35]) usb_blank();
    color([0.22, 0.26, 0.28]) translate([60, -70, -35]) usb_blank();
    color([0.17, 0.20, 0.22])
        translate([-120, -230, 130])
            rotate([180, 0, 0]) front_panel_upper_printable();
    color([0.15, 0.18, 0.20])
        translate([120, -230, -25])
            rotate([180, 0, 0]) front_panel_lower_printable();
}
