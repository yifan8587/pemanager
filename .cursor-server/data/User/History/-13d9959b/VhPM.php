<?php

/*  
    Proxmox VE for WHMCS - Addon/Server Modules for WHMCS (& PVE)
    https://github.com/The-Network-Crew/Proxmox-VE-for-WHMCS/
    File: /modules/addons/pvewhmcs/hooks.php (WHMCS Hooks)

    Copyright (C) The Network Crew Pty Ltd (TNC) & Co.

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>. 
*/

if (!defined("WHMCS"))
    die("This file cannot be accessed directly");

use Illuminate\Database\Capsule\Manager as Capsule;

/**
 * Sync PVE LXC templates to WHMCS product custom fields.
 *
 * For every product using the pvewhmcs server module, this function
 * creates or updates a dropdown custom field named "OS Template" whose
 * options mirror the LXC/CT entries in mod_pvewhmcs_templates.
 * This allows customers to choose their OS during the order process.
 */
function pvewhmcs_sync_os_template_custom_fields() {
    try {
        // Fetch all LXC/CT templates registered in Module Config > Templates
        $templates = Capsule::table('mod_pvewhmcs_templates')
            ->whereIn('guest', ['ct', 'lxc'])
            ->orderBy('title', 'asc')
            ->get();

        if ($templates->isEmpty()) return;

        // Build comma-separated options string for WHMCS dropdown custom field
        $options_parts = ['-- 请选择操作系统 --'];
        foreach ($templates as $tpl) {
            $options_parts[] = trim($tpl->title);
        }
        $options_str = implode(',', $options_parts);

        // Get all products that use pvewhmcs as their server module
        $product_ids = Capsule::table('tblproducts')
            ->where('servertype', 'pvewhmcs')
            ->pluck('id');

        foreach ($product_ids as $pid) {
            $existing = Capsule::table('tblcustomfields')
                ->where('type', 'product')
                ->where('relid', $pid)
                ->where('fieldname', 'OS Template')
                ->first();

            if ($existing) {
                // Update existing field options to reflect current templates
                Capsule::table('tblcustomfields')
                    ->where('id', $existing->id)
                    ->update(['fieldoptions' => $options_str]);
            } else {
                // Create the "OS Template" custom field for this product
                Capsule::table('tblcustomfields')->insert([
                    'type'         => 'product',
                    'relid'        => $pid,
                    'fieldname'    => 'OS Template',
                    'fieldtype'    => 'dropdown',
                    'fieldoptions' => $options_str,
                    'description'  => '请选择您的操作系统版本',
                    'defaultvalue' => '',
                    'showorder'    => 1,
                    'showinvoice'  => 0,
                    'adminonly'    => '',
                    'required'     => 'on',
                ]);
            }
        }
    } catch (\Exception $e) {
        // Silent fail — table may not exist yet (module not activated)
    }
}

/**
 * Hook: Sync OS templates and inject cart-page customizations.
 *
 * On every client-area page render we:
 *  1. Sync PVE LXC templates → WHMCS "OS Template" custom field (on cart pages).
 *  2. Inject a small JS snippet that hides the NS1/NS2 prefix fields that
 *     WHMCS automatically shows for server-module products but are irrelevant
 *     for VPS products managed by Proxmox VE.
 */
add_hook('ClientAreaFooterOutput', 1, function($vars) {
    $uri = isset($_SERVER['REQUEST_URI']) ? $_SERVER['REQUEST_URI'] : '';

    // Detect cart / order configure pages (WHMCS 7 and 8 URL patterns)
    $on_cart = (
        strpos($uri, 'cart.php') !== false ||
        strpos($uri, '/cart')    !== false ||
        strpos($uri, '/order')   !== false
    );

    if (!$on_cart) {
        return '';
    }

    // Keep custom field options fresh whenever the cart is visited
    pvewhmcs_sync_os_template_custom_fields();

    // JavaScript injected into page footer:
    //   - Hides Nameserver prefix fields (NS1/NS2) that are irrelevant for VPS
    //   - Runs immediately on DOMContentLoaded and also after a short delay
    //     to handle pages that render form fields dynamically
    return '<script>
(function () {
    "use strict";

    function hideNsFields() {
        ["ns1prefix", "ns2prefix"].forEach(function (fieldName) {
            var input = document.querySelector("input[name=\"" + fieldName + "\"]");
            if (!input) return;

            // Walk up the DOM tree to find the enclosing .form-group or <tr>
            var node = input;
            for (var i = 0; i < 8; i++) {
                node = node.parentElement;
                if (!node) break;
                var tag = node.tagName ? node.tagName.toLowerCase() : "";
                if (
                    node.classList.contains("form-group") ||
                    node.classList.contains("row") ||
                    tag === "tr" ||
                    tag === "li"
                ) {
                    node.style.display = "none";
                    break;
                }
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", hideNsFields);
    } else {
        hideNsFields();
    }
    // Extra pass for dynamically-rendered pages
    setTimeout(hideNsFields, 400);
    setTimeout(hideNsFields, 1200);
})();
</script>';
});

// ── Existing hooks (kept for compatibility) ──────────────────────────────────

function pvewhmcs_hook_login($vars) {
    // Sync templates when a client logs in (keeps options current)
    pvewhmcs_sync_os_template_custom_fields();
}
add_hook("ClientLogin", 1, "pvewhmcs_hook_login");

function pvewhmcs_hook_logout($vars) {
    // Your code goes here
}
add_hook("ClientLogout", 1, "pvewhmcs_hook_logout");
