{* Proxmox VE for WHMCS - Client Area Template *}

<style>
.pve-client-area {
	font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}
.pve-header-panel {
	background: #fafafa;
	border: 1px solid #e0e0e0;
	border-radius: 8px;
	padding: 20px;
	margin-bottom: 20px;
}
.pve-status-section {
	display: flex;
	align-items: center;
	gap: 20px;
	flex-wrap: nowrap;
}
.pve-vm-icons {
	display: flex;
	flex-direction: column;
	align-items: center;
	gap: 8px;
	flex-shrink: 0;
}
.pve-vm-icons img {
	max-width: 56px;
	height: auto;
}
.pve-status-badge {
	text-align: center;
	padding: 14px 18px;
	background: #fff;
	border: 1px solid #e0e0e0;
	border-radius: 8px;
	min-width: 95px;
	flex-shrink: 0;
}
.pve-status-badge img {
	max-width: 44px;
	margin-bottom: 7px;
}
.pve-status-badge .status-text {
	display: block;
	text-transform: uppercase;
	font-weight: 700;
	font-size: 13px;
	color: #5c3d7a;
	margin-bottom: 3px;
}
.pve-status-badge .uptime-text {
	font-size: 12px;
	color: #555;
}
.pve-gauges {
	display: flex;
	gap: 10px;
	flex-wrap: nowrap;
	flex: 1;
	justify-content: flex-end;
}
.pve-gauge-item {
	background: #fff;
	border: 1px solid #e0e0e0;
	border-radius: 8px;
	padding: 12px;
	text-align: center;
	min-width: 75px;
}
.pve-gauge-item .circle {
	margin: 0 auto;
}
.pve-gauge-item strong {
	display: block;
	margin-top: 7px;
	font-size: 12px;
	color: #555;
}

/* Specs Table */
.pve-specs-table {
	width: 100%;
	border-collapse: separate;
	border-spacing: 0;
	border: 1px solid #e0e0e0;
	border-radius: 8px;
	overflow: hidden;
	margin-bottom: 20px;
	background: #fff;
	font-size: 14px;
}
.pve-specs-table tr:not(:last-child) {
	border-bottom: 1px solid #eee;
}
.pve-specs-table td {
	padding: 13px 16px;
	vertical-align: top;
	font-size: 14px;
	line-height: 1.5;
}
.pve-specs-table td:first-child {
	background: #f8f8f8;
	width: 180px;
	font-weight: 500;
	color: #444;
	border-right: 1px solid #eee;
}
.pve-specs-table td:last-child {
	color: #333;
}
.pve-specs-table .spec-label {
	font-weight: 600;
	font-size: 14px;
	color: #5c3d7a;
}
.pve-specs-table .spec-sublabel {
	font-size: 12px;
	color: #555;
	font-weight: normal;
}
.pve-specs-table .spec-value {
	font-weight: 600;
	font-size: 14px;
	color: #333;
}
.pve-specs-table .spec-detail {
	font-size: 14px;
	color: #555;
	margin-top: 3px;
}
.pve-specs-table code {
	background: #f4f0f7;
	padding: 2px 6px;
	border-radius: 3px;
	font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
	font-size: 13px;
	color: #5c3d7a;
}

/* Statistics Section */
.pve-stats-section {
	margin-top: 25px;
}
.pve-stats-section h4 {
	color: #5c3d7a;
	font-weight: 600;
	margin-bottom: 15px;
	padding-bottom: 10px;
	border-bottom: 2px solid #5c3d7a;
}
.pve-stats-tabs {
	display: flex;
	gap: 5px;
	margin-bottom: 0;
	padding: 0;
	list-style: none;
	border-bottom: 1px solid #ddd;
}
.pve-stats-tabs li {
	margin: 0;
}
.pve-stats-tabs li a {
	display: block;
	padding: 10px 20px;
	text-decoration: none;
	color: #666;
	background: #f5f5f5;
	border: 1px solid #ddd;
	border-bottom: none;
	border-radius: 6px 6px 0 0;
	font-weight: 500;
	font-size: 13px;
	transition: all 0.2s ease;
}
.pve-stats-tabs li a:hover {
	background: #eee;
	color: #5c3d7a;
}
.pve-stats-tabs li.active a {
	background: #f5f5f5;
	color: #666;
	border-color: #ddd;
}
.pve-stats-content {
	background: #fff;
	border: 1px solid #ddd;
	border-top: none;
	border-radius: 0 0 8px 8px;
	padding: 20px;
}
.pve-stats-content .tab-pane {
	display: none;
}
.pve-stats-content .tab-pane.active {
	display: block;
}
.pve-graphs-grid {
	display: flex;
	flex-direction: column;
	gap: 15px;
}
.pve-graphs-grid img {
	width: 100%;
	border-radius: 6px;
	border: 1px solid #eee;
}
/* Responsive: Large screens - maximize graph space */
@media (min-width: 1200px) {
	.pve-status-section {
		gap: 25px;
	}
	.pve-gauges {
		gap: 15px;
	}
	.pve-gauge-item {
		padding: 14px;
		min-width: 80px;
	}
	.pve-graphs-grid img {
		max-width: 100%;
	}
}

/* Responsive: Medium screens (tablets) */
@media (min-width: 769px) and (max-width: 1199px) {
	.pve-status-section {
		gap: 15px;
	}
	.pve-vm-icons img {
		max-width: 48px;
	}
	.pve-gauges {
		gap: 8px;
	}
	.pve-gauge-item {
		padding: 10px;
		min-width: 65px;
	}
}

/* Responsive: Small screens (mobile) */
@media (max-width: 768px) {
	.pve-status-section {
		flex-direction: column;
		text-align: center;
		gap: 15px;
	}
	.pve-status-section > * {
		flex-shrink: 1;
	}
	.pve-vm-icons {
		flex-direction: row;
		gap: 15px;
	}
	.pve-gauges {
		flex-wrap: wrap;
		justify-content: center;
		width: 100%;
	}
	.pve-gauge-item {
		flex: 1 1 calc(50% - 8px);
		max-width: calc(50% - 8px);
	}
	.pve-specs-table td:first-child {
		width: 120px;
	}
}

/* Alert styling */
.pve-alert-warning {
	background: #fff3cd;
	border: 1px solid #ffc107;
	border-radius: 6px;
	padding: 15px;
	color: #856404;
	font-size: 13px;
}
.pve-alert-warning i {
	margin-right: 8px;
}

/* Root Password Reset Panel */
.pve-passwd-panel {
	background: #fafafa;
	border: 1px solid #e0e0e0;
	border-radius: 8px;
	margin-bottom: 20px;
	overflow: hidden;
}
.pve-passwd-header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 14px 20px;
	cursor: pointer;
	user-select: none;
	background: #f4f0f7;
	border-bottom: 1px solid #e0e0e0;
}
.pve-passwd-header:hover { background: #ede8f3; }
.pve-passwd-header h5 {
	margin: 0;
	font-size: 14px;
	font-weight: 600;
	color: #5c3d7a;
}
.pve-passwd-header .toggle-icon {
	font-size: 14px;
	color: #5c3d7a;
	transition: transform 0.25s;
}
.pve-passwd-body {
	padding: 20px;
	display: none;
}
.pve-passwd-body .form-group { margin-bottom: 14px; }
.pve-passwd-body label { font-size: 13px; font-weight: 500; color: #444; margin-bottom: 5px; display: block; }
.pve-passwd-body input[type="password"] {
	width: 100%;
	padding: 8px 12px;
	border: 1px solid #ccc;
	border-radius: 5px;
	font-size: 14px;
	box-sizing: border-box;
}
.pve-passwd-body input[type="password"]:focus {
	border-color: #802DBC;
	outline: none;
	box-shadow: 0 0 0 2px rgba(128,45,188,.15);
}
.pve-passwd-btn {
	background: #5c3d7a;
	color: #fff;
	border: none;
	padding: 9px 22px;
	border-radius: 5px;
	font-size: 13px;
	font-weight: 600;
	cursor: pointer;
	transition: background .2s;
}
.pve-passwd-btn:hover  { background: #802DBC; }
.pve-passwd-btn:disabled { background: #aaa; cursor: not-allowed; }
.pve-passwd-msg {
	margin-top: 12px;
	padding: 9px 14px;
	border-radius: 5px;
	font-size: 13px;
	display: none;
}
.pve-passwd-msg.success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
.pve-passwd-msg.error   { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
</style>

<div class="pve-client-area">
	{* Header Panel with VM Type, Status, and Gauges *}
	<div class="pve-header-panel">
		<div class="pve-status-section">
			{* VM Type & OS Icons *}
			<div class="pve-vm-icons">
				<img src="./modules/servers/pvewhmcs/img/{$vm_config['vtype']}.png" alt="{$vm_config['vtype']}" title="Type: {$vm_config['vtype']}"/>
				<img src="./modules/servers/pvewhmcs/img/os/{$vm_config['ostype']}.png" alt="{$vm_config['ostype']}" title="OS: {$vm_config['ostype']}"/>
			</div>
			
			{* Status Badge *}
			<div class="pve-status-badge">
				<img src="./modules/servers/pvewhmcs/img/{$vm_status['status']}.png" alt="{$vm_status['status']}"/>
				<span class="status-text">{$vm_status['status']}</span>
				<span class="uptime-text">Up {$vm_status['uptime']}</span>
			</div>
			
			{* Resource Gauges *}
			<div class="pve-gauges">
				<script src="./modules/servers/pvewhmcs/js/CircularLoader.js"></script>
				<div class="pve-gauge-item">
					<div id="c1" class="circle" data-percent="{$vm_status['cpu']}"></div>
					<strong>CPU</strong>
				</div>
				<div class="pve-gauge-item">
					<div id="c2" class="circle" data-percent="{$vm_status['memusepercent']}"></div>
					<strong>RAM</strong>
				</div>
				<div class="pve-gauge-item">
					<div id="c3" class="circle" data-percent="{$vm_status['diskusepercent']}"></div>
					<strong>Disk</strong>
				</div>
				<div class="pve-gauge-item">
					<div id="c4" class="circle" data-percent="{$vm_status['swapusepercent']}"></div>
					<strong>Swap</strong>
				</div>
			</div>
		</div>
	</div>
	
	<script>
	$(document).ready(function() {
		$('.circle').each(function(){
			$(this).circularloader({
				progressPercent: $(this).attr("data-percent"),
				fontSize: "12px",
				radius: 27,
				progressBarWidth: 7,
				progressBarBackground: "#D6B1F9",
				progressBarColor: "#802DBC",
			});
		});
	});
	</script>

	{* Specifications Table *}
	<table class="pve-specs-table">
		<tr>
			<td><span class="spec-label">Memory</span> <span class="spec-sublabel">(RAM)</span></td>
			<td><span class="spec-value">{$vm_config['memory']}MB</span></td>
		</tr>
		<tr>
			<td><span class="spec-label">Compute</span> <span class="spec-sublabel">(CPU)</span></td>
			<td>
				<span class="spec-value">{$vm_config['cores']} core(s)</span>
				<div class="spec-detail">on {$vm_config['sockets']} socket(s)</div>
			</td>
		</tr>
		<tr>
			<td><span class="spec-label">Storage</span> <span class="spec-sublabel">(SSD/HDD)</span></td>
			<td>
				{if $vm_config['rootfs']}
					{assign var="rootfs_parts" value=","|explode:$vm_config['rootfs']}
					{foreach from=$rootfs_parts item=rpart}
						{if $rpart|strpos:"size=" !== false}<span class="spec-value">{$rpart|replace:'size=':''}</span> <span class="spec-detail">(rootfs)</span>{/if}
					{/foreach}
				{/if}
				{if $vm_config['ide0']}
					{assign var="ide0_parts" value=","|explode:$vm_config['ide0']}
					{foreach from=$ide0_parts item=ipart}
						{if $ipart|strpos:"size=" !== false}<div class="spec-detail"><span class="spec-value">{$ipart|replace:'size=':''}</span> (ide0)</div>{/if}
					{/foreach}
				{/if}
				{if $vm_config['scsi0']}
					{assign var="scsi0_parts" value=","|explode:$vm_config['scsi0']}
					{foreach from=$scsi0_parts item=spart}
						{if $spart|strpos:"size=" !== false}<div class="spec-detail"><span class="spec-value">{$spart|replace:'size=':''}</span> (scsi0)</div>{/if}
					{/foreach}
				{/if}
				{if $vm_config['virtio0']}
					{assign var="virtio0_parts" value=","|explode:$vm_config['virtio0']}
					{foreach from=$virtio0_parts item=vpart}
						{if $vpart|strpos:"size=" !== false}<div class="spec-detail"><span class="spec-value">{$vpart|replace:'size=':''}</span> (virtio0)</div>{/if}
					{/foreach}
				{/if}
			</td>
		</tr>
		<tr>
			<td><span class="spec-label">Boot Order</span></td>
			<td><span class="spec-value">{($vm_config['boot']|replace:'order=':''|replace:';':' → ')}</span></td>
		</tr>
		<tr>
			<td><span class="spec-label">IPv4</span> <span class="spec-sublabel">(Networking)</span></td>
			<td>
				<span class="spec-value">{$vm_config['ipv4']}</span>
				<div class="spec-detail">Mask: {$vm_config['netmask4']} &bull; Gateway: {$vm_config['gateway4']}</div>
			</td>
		</tr>
		<tr>
			<td><span class="spec-label">IP Config</span> <span class="spec-sublabel">(IPv4/v6)</span></td>
			<td>
				{if $vm_config['ipconfig0']}<div class="spec-detail"><strong>NIC #0:</strong> {($vm_config['ipconfig0']|replace:',':' &bull; '|replace:'=':': ')}</div>{/if}
				{if $vm_config['ipconfig1']}<div class="spec-detail"><strong>NIC #1:</strong> {($vm_config['ipconfig1']|replace:',':' &bull; '|replace:'=':': ')}</div>{/if}
			</td>
		</tr>
		<tr>
			<td><span class="spec-label">NIC #0</span> <span class="spec-sublabel">(Primary)</span></td>
			<td>
				{assign var="net0_parts" value=","|explode:$vm_config['net0']}
				{foreach from=$net0_parts item=part name=netloop}
					{if $part|strpos:"=" !== false}
						{assign var="kv" value="="|explode:$part}
						{if $kv[0] == 'virtio' || $kv[0] == 'e1000' || $kv[0] == 'rtl8139'}
							<div class="spec-detail"><strong>{$kv[0]}</strong>: <code>{$kv[1]}</code></div>
						{elseif $kv[0] == 'bridge' || $kv[0] == 'link_down' || $kv[0] == 'firewall' || $kv[0] == 'tag'}
							<div class="spec-detail"><strong>{$kv[0]}</strong>: {$kv[1]}</div>
						{/if}
					{/if}
				{/foreach}
			</td>
		</tr>
		{if $vm_config['net1']}
		<tr>
			<td><span class="spec-label">NIC #1</span> <span class="spec-sublabel">(Secondary)</span></td>
			<td>
				{assign var="net1_parts" value=","|explode:$vm_config['net1']}
				{foreach from=$net1_parts item=part name=netloop}
					{if $part|strpos:"=" !== false}
						{assign var="kv" value="="|explode:$part}
						{if $kv[0] == 'virtio' || $kv[0] == 'e1000' || $kv[0] == 'rtl8139'}
							<div class="spec-detail"><strong>{$kv[0]}</strong>: <code>{$kv[1]}</code></div>
						{elseif $kv[0] == 'bridge' || $kv[0] == 'link_down' || $kv[0] == 'firewall' || $kv[0] == 'tag'}
							<div class="spec-detail"><strong>{$kv[0]}</strong>: {$kv[1]}</div>
						{/if}
					{/if}
				{/foreach}
			</td>
		</tr>
		{/if}
		<tr>
			<td><span class="spec-label">Config</span> <span class="spec-sublabel">(Tweaks)</span></td>
			<td><span class="spec-detail"><strong>On-boot?</strong> {if $vm_config['onboot']}Yes!{else}No (Contact Support){/if}</span></td>
		</tr>
		{if $vm_config['sshkeys']}
		<tr>
			<td><span class="spec-label">SSH Keys</span> <span class="spec-sublabel">(Public)</span></td>
			<td><div class="spec-detail" style="word-break:break-all;">{$vm_config['sshkeys']}</div></td>
		</tr>
		{/if}
		<tr>
			<td><span class="spec-label">Kernel</span> <span class="spec-sublabel">(OS)</span></td>
			<td><span class="spec-value">{$vm_config['ostype']}</span></td>
		</tr>
	</table>

	{* Root Password Reset Panel *}
	<div class="pve-passwd-panel" id="pvePasswdPanel">
		<div class="pve-passwd-header" onclick="pvePwdToggle()">
			<h5><i class="fa fa-key"></i>&nbsp; 设置 / 重置 Root 密码</h5>
			<span class="toggle-icon" id="pvePwdIcon"><i class="fa fa-chevron-down"></i></span>
		</div>
		<div class="pve-passwd-body" id="pvePwdBody">
			<div class="form-group">
				<label for="pveNewPwd">新密码 <small style="color:#888">（至少8位字符）</small></label>
				<input type="password" id="pveNewPwd" placeholder="输入新密码" autocomplete="new-password"/>
			</div>
			<div class="form-group">
				<label for="pveConfirmPwd">确认新密码</label>
				<input type="password" id="pveConfirmPwd" placeholder="再次输入新密码" autocomplete="new-password"/>
			</div>
			<button class="pve-passwd-btn" id="pvePwdBtn" onclick="pveSubmitPassword()">
				<i class="fa fa-save"></i> 保存密码
			</button>
			<div class="pve-passwd-msg" id="pvePwdMsg"></div>
		</div>
	</div>

	<script>
	(function () {
		var SERVICE_ID = {$params.serviceid|intval};
		var ENDPOINT   = "./modules/servers/pvewhmcs/pve_passwd.php";

		window.pvePwdToggle = function () {
			var body = document.getElementById("pvePwdBody");
			var icon = document.getElementById("pvePwdIcon");
			var open = body.style.display === "block";
			body.style.display = open ? "none" : "block";
			icon.style.transform = open ? "" : "rotate(180deg)";
		};

		window.pveSubmitPassword = function () {
			var np  = document.getElementById("pveNewPwd").value.trim();
			var cp  = document.getElementById("pveConfirmPwd").value.trim();
			var msg = document.getElementById("pvePwdMsg");
			var btn = document.getElementById("pvePwdBtn");

			msg.style.display = "none";
			msg.className = "pve-passwd-msg";

			if (np.length < 8) {
				msg.textContent = "密码长度至少需要8位字符。";
				msg.className = "pve-passwd-msg error";
				msg.style.display = "block";
				return;
			}
			if (np !== cp) {
				msg.textContent = "两次输入的密码不一致，请重新输入。";
				msg.className = "pve-passwd-msg error";
				msg.style.display = "block";
				return;
			}

			btn.disabled = true;
			btn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> 正在设置…';

			var payload = JSON.stringify({ service_id: SERVICE_ID, new_password: np });

			var xhr = new XMLHttpRequest();
			xhr.open("POST", ENDPOINT, true);
			xhr.setRequestHeader("Content-Type", "application/json");
			xhr.onreadystatechange = function () {
				if (xhr.readyState !== 4) return;
				btn.disabled = false;
				btn.innerHTML = '<i class="fa fa-save"></i> 保存密码';
				try {
					var res = JSON.parse(xhr.responseText);
					if (res.success) {
						msg.textContent = "✓ Root 密码已成功更新！";
						msg.className = "pve-passwd-msg success";
						document.getElementById("pveNewPwd").value = "";
						document.getElementById("pveConfirmPwd").value = "";
					} else {
						msg.textContent = "✗ 错误：" + (res.error || "未知错误");
						msg.className = "pve-passwd-msg error";
					}
				} catch (e) {
					msg.textContent = "✗ 服务器返回了无效响应，请重试或联系技术支持。";
					msg.className = "pve-passwd-msg error";
				}
				msg.style.display = "block";
			};
			xhr.onerror = function () {
				btn.disabled = false;
				btn.innerHTML = '<i class="fa fa-save"></i> 保存密码';
				msg.textContent = "✗ 网络错误，请检查连接后重试。";
				msg.className = "pve-passwd-msg error";
				msg.style.display = "block";
			};
			xhr.send(payload);
		};
	})();
	</script>

	{* Statistics Section *}
	{if ($smarty.get.a eq 'vmStat')}
	<div class="pve-stats-section">
		<h4><i class="fa fa-line-chart"></i> Guest Statistics</h4>
		
		{if $vm_statistics['cpu']['day']}
		<ul class="pve-stats-tabs" role="tablist">
			<li class="active"><a data-toggle="tab" role="tab" href="#dailystat">Daily</a></li>
			<li><a data-toggle="tab" role="tab" href="#weeklystat">Weekly</a></li>
			<li><a data-toggle="tab" role="tab" href="#monthlystat">Monthly</a></li>
			<li><a data-toggle="tab" role="tab" href="#yearlystat">Yearly</a></li>
		</ul>
		<div class="pve-stats-content tab-content">
			<div id="dailystat" class="tab-pane active">
				<div class="pve-graphs-grid">
					<img src="data:image/png;base64,{$vm_statistics['cpu']['day']}" alt="CPU (Daily)"/>
					<img src="data:image/png;base64,{$vm_statistics['mem']['day']}" alt="Memory (Daily)"/>
					<img src="data:image/png;base64,{$vm_statistics['netinout']['day']}" alt="Network I/O (Daily)"/>
					<img src="data:image/png;base64,{$vm_statistics['diskrw']['day']}" alt="Disk I/O (Daily)"/>
				</div>
			</div>
			<div id="weeklystat" class="tab-pane">
				<div class="pve-graphs-grid">
					<img src="data:image/png;base64,{$vm_statistics['cpu']['week']}" alt="CPU (Weekly)"/>
					<img src="data:image/png;base64,{$vm_statistics['mem']['week']}" alt="Memory (Weekly)"/>
					<img src="data:image/png;base64,{$vm_statistics['netinout']['week']}" alt="Network I/O (Weekly)"/>
					<img src="data:image/png;base64,{$vm_statistics['diskrw']['week']}" alt="Disk I/O (Weekly)"/>
				</div>
			</div>
			<div id="monthlystat" class="tab-pane">
				<div class="pve-graphs-grid">
					<img src="data:image/png;base64,{$vm_statistics['cpu']['month']}" alt="CPU (Monthly)"/>
					<img src="data:image/png;base64,{$vm_statistics['mem']['month']}" alt="Memory (Monthly)"/>
					<img src="data:image/png;base64,{$vm_statistics['netinout']['month']}" alt="Network I/O (Monthly)"/>
					<img src="data:image/png;base64,{$vm_statistics['diskrw']['month']}" alt="Disk I/O (Monthly)"/>
				</div>
			</div>
			<div id="yearlystat" class="tab-pane">
				<div class="pve-graphs-grid">
					<img src="data:image/png;base64,{$vm_statistics['cpu']['year']}" alt="CPU (Yearly)"/>
					<img src="data:image/png;base64,{$vm_statistics['mem']['year']}" alt="Memory (Yearly)"/>
					<img src="data:image/png;base64,{$vm_statistics['netinout']['year']}" alt="Network I/O (Yearly)"/>
					<img src="data:image/png;base64,{$vm_statistics['diskrw']['year']}" alt="Disk I/O (Yearly)"/>
				</div>
			</div>
		</div>
		{else}
		<div class="pve-alert-warning">
			<i class="fa fa-exclamation-triangle"></i>
			Stats Error: RRD Unavailable. Ask Support to upgrade guest RRD Data from 2.x to 9.0 format on their Node/s!
		</div>
		{/if}
	</div>
	{/if}
</div>
