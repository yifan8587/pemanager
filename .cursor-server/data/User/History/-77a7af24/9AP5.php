<?php
/**
 * Proxmox VE for WHMCS – Client-Area Root Password Reset Endpoint
 *
 * Accepts a JSON POST from the client area template, validates the WHMCS
 * session, verifies service ownership, then uses the PVE API to update the
 * root password of the corresponding VM/CT.
 *
 * Request (POST, JSON body or form-encoded):
 *   service_id   int     WHMCS service / hosting ID
 *   new_password string  New root password (plain text, min 8 chars)
 *
 * Response (JSON):
 *   { "success": true }
 *   { "success": false, "error": "..." }
 */

// Bootstrap WHMCS so we get Capsule, localAPI, session, etc.
define('CLIENTAREA', true);
$whmcs_root = dirname(dirname(dirname(dirname(__FILE__))));
require_once $whmcs_root . '/init.php';

use Illuminate\Database\Capsule\Manager as Capsule;

// Require the PVE API client
require_once dirname(dirname(__FILE__)) . '/addons/pvewhmcs/proxmox.php';

header('Content-Type: application/json; charset=utf-8');

// ── 1. Validate WHMCS client session ─────────────────────────────────────────
$uid = isset($_SESSION['uid']) ? (int)$_SESSION['uid'] : 0;
if ($uid <= 0) {
    echo json_encode(['success' => false, 'error' => '未登录，请先登录您的账户。']);
    exit;
}

// ── 2. Parse & sanitise input ─────────────────────────────────────────────────
$raw = file_get_contents('php://input');
$data = json_decode($raw, true);
if (!$data) {
    $data = $_POST;
}

$service_id   = isset($data['service_id'])   ? (int)$data['service_id']       : 0;
$new_password = isset($data['new_password']) ? trim($data['new_password'])     : '';

if ($service_id <= 0) {
    echo json_encode(['success' => false, 'error' => '无效的服务ID。']);
    exit;
}
if (strlen($new_password) < 8) {
    echo json_encode(['success' => false, 'error' => '密码长度至少需要8位字符。']);
    exit;
}

// ── 3. Verify the service belongs to this client ─────────────────────────────
$hosting = Capsule::table('tblhosting')
    ->where('id', $service_id)
    ->where('userid', $uid)
    ->where('domainstatus', 'Active')
    ->first();

if (!$hosting) {
    echo json_encode(['success' => false, 'error' => '服务不存在或无权操作。']);
    exit;
}

// Confirm the service uses pvewhmcs server module
$server = Capsule::table('tblservers')->where('id', $hosting->server)->first();
if (!$server) {
    echo json_encode(['success' => false, 'error' => '找不到关联的服务器配置。']);
    exit;
}

// ── 4. Load VM record from pvewhmcs table ────────────────────────────────────
$guest = Capsule::table('mod_pvewhmcs_vms')->where('id', $service_id)->first();
if (!$guest) {
    echo json_encode(['success' => false, 'error' => '找不到与该服务关联的虚拟机记录。']);
    exit;
}

// ── 5. Connect to PVE API ────────────────────────────────────────────────────
$serverip       = $server->ipaddress;
$serverusername = $server->username;

// Decrypt server password via WHMCS localAPI
$dec = localAPI('DecryptPassword', ['password2' => $server->password]);
$serverpassword = isset($dec['password']) ? $dec['password'] : '';

if (empty($serverpassword)) {
    echo json_encode(['success' => false, 'error' => '无法获取服务器凭证，请联系技术支持。']);
    exit;
}

try {
    $proxmox = new PVE2_API($serverip, $serverusername, 'pam', $serverpassword);
    if (!$proxmox->login()) {
        echo json_encode(['success' => false, 'error' => 'PVE API 登录失败，请联系技术支持。']);
        exit;
    }

    // Find which node the guest lives on
    $cluster = $proxmox->get('/cluster/resources');
    $guest_node = null;
    if (is_array($cluster)) {
        foreach ($cluster as $res) {
            if (isset($res['vmid'], $res['type'], $res['node'])
                && $res['vmid'] == $guest->vmid
                && $res['type'] === $guest->vtype
            ) {
                $guest_node = $res['node'];
                break;
            }
        }
    }
    // Fallback: first node
    if (empty($guest_node)) {
        $nodes = $proxmox->get_node_list();
        $guest_node = is_array($nodes) && !empty($nodes) ? $nodes[0] : null;
    }
    if (empty($guest_node)) {
        echo json_encode(['success' => false, 'error' => '无法确定虚拟机所在节点。']);
        exit;
    }

    // ── 6. Apply new password via PVE API ─────────────────────────────────────
    $config_path = '/nodes/' . $guest_node . '/' . $guest->vtype . '/' . $guest->vmid . '/config';

    if ($guest->vtype === 'lxc') {
        // LXC: direct root password change (takes effect immediately)
        $response = $proxmox->post($config_path, ['password' => $new_password]);
    } else {
        // QEMU: update cloud-init cipassword, then regenerate the cloud-init drive
        $proxmox->post($config_path, ['cipassword' => $new_password]);
        // Trigger cloud-init drive regeneration (PVE 6.3+)
        $regen_path = '/nodes/' . $guest_node . '/qemu/' . $guest->vmid . '/cloudinit';
        $proxmox->put($regen_path, []);
    }

    // Also update the service password in WHMCS so the admin panel reflects it
    localAPI('UpdateClientProduct', [
        'serviceid' => $service_id,
        'password'  => $new_password,
    ]);

    echo json_encode(['success' => true]);

} catch (Exception $e) {
    echo json_encode(['success' => false, 'error' => 'PVE API 错误：' . $e->getMessage()]);
}
