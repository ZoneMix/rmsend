# Wi-Fi delivery with Tailscale SSH

This reproduces the maintainer's **reMarkable 2** setup, inspected on September
30, 2026: firmware **3.28.0.172**, ARMv7, Tailscale **1.102.4**, userspace networking,
and Tailscale SSH. The binaries and private state live under `/home/root/tailscale`;
systemd starts the daemon. rmsend uses ordinary `ssh` to the tablet's tailnet IP.
Other tablet models and firmware versions are untested.

These are first-time installation steps. If Tailscale is already installed,
inspect its service, binary paths, and version before copying files. Preserve
the existing state and avoid overwriting binaries while their daemon is running.

The tested kernel has no `/dev/net/tun`. Tailscale's
[userspace networking mode](https://tailscale.com/docs/concepts/userspace-networking)
works without it. Enabling [Tailscale SSH](https://tailscale.com/docs/features/tailscale-ssh)
provides the inbound SSH server in that mode. There is no need to patch the
kernel, configure a SOCKS proxy on your computer, or expose port 22 to the internet.

## 1. Prepare both devices

On your **computer**, clone rmsend and install its prerequisites as described in
[the README](../README.md). Keep the checkout available for the service example.
Install [Tailscale](https://tailscale.com/docs/install) on the computer and sign in.
The macOS GUI app is sufficient; rmsend does not require a `tailscale` CLI on
the computer. Linux users can follow Tailscale's distribution instructions.

On the **tablet**, join Wi-Fi through Settings. It needs internet access to join
the tailnet. Establish and keep a working USB SSH session using
[the bootstrap guide](setup.md#ssh-over-usb-bootstrap-and-recovery). Tailscale
setup happens through that session, so a failure cannot strand you remotely.
Local Wi-Fi SSH is optional for this path.

Run these on the **tablet**:

```bash
uname -m
df -h / /home
```

For reMarkable 2, expect `armv7l`: choose Tailscale's **arm**, not arm64, archive.
If your architecture differs, stop and check support for your model. Keep the
binaries on `/home`, which has space for them; the small root partition does not.
Allow roughly 150 MB free on `/home` for binaries and installation overhead.

## 2. Download and verify the ARM binaries

On your **computer**, from the rmsend checkout, create a scratch directory and
download the pinned, tested release from the
[official static package server](https://pkgs.tailscale.com/stable/):

```bash
mkdir -p /tmp/rmsend-tailscale-1.102.4
cd /tmp/rmsend-tailscale-1.102.4
curl --fail --location --output tailscale_1.102.4_arm.tgz \
  https://pkgs.tailscale.com/stable/tailscale_1.102.4_arm.tgz
```

The archive's SHA-256 must be:

```text
b981a59cb85fb923ee6e1860ee6934772c83a840a6627f0dbfd7711ed690b869
```

Check it with `shasum -a 256 tailscale_1.102.4_arm.tgz` on macOS or
`sha256sum tailscale_1.102.4_arm.tgz` on Linux. Stop if it does not match.
The package server also publishes the
[checksum](https://pkgs.tailscale.com/stable/tailscale_1.102.4_arm.tgz.sha256).
For a future release, deliberately choose its version and verify its own checksum;
this example does not silently install whatever becomes latest.

Extract and copy over USB from the **computer**:

```bash
tar -xzf tailscale_1.102.4_arm.tgz
ssh remarkable-usb 'mkdir -p /home/root/tailscale/bin'
scp -O tailscale_1.102.4_arm/tailscale tailscale_1.102.4_arm/tailscaled \
  remarkable-usb:/home/root/tailscale/bin/
```

`scp -O` selects legacy SCP because the tablet's bundled Dropbear server may not
provide the SFTP subsystem modern scp uses by default. USB SSH still verifies
the tablet's host key and authenticates with your installed key.

On the **tablet**, prepare the private state directory and check the binary:

```bash
chmod 755 /home/root/tailscale/bin/tailscale /home/root/tailscale/bin/tailscaled
mkdir -p /home/root/tailscale/state
chmod 700 /home/root/tailscale/state
/home/root/tailscale/bin/tailscale version
```

Expect version `1.102.4`. The state directory will contain device credentials.
Keep it private; never commit it, share it, or copy it onto a different tablet.
The binary installation follows Tailscale's
[static installation method](https://tailscale.com/docs/install/linux#static-binaries),
with paths adjusted for the tablet's storage layout.

## 3. Install the startup service

Return to the rmsend checkout on the **computer** and copy the included example:

```bash
scp -O examples/tailscaled.service remarkable-usb:/home/root/tailscale/tailscaled.service
```

On the **tablet**:

```bash
cp /home/root/tailscale/tailscaled.service /etc/systemd/system/tailscaled.service
chmod 644 /etc/systemd/system/tailscaled.service
systemctl daemon-reload
systemctl enable --now tailscaled.service
systemctl is-active tailscaled.service
```

Expect `active`. The [service file](../examples/tailscaled.service) uses
`--tun=userspace-networking`, stores credentials on `/home`, creates the runtime
socket directory, waits for the home mount, and restarts after a daemon failure.
It contains no login credentials. If a Tailscale service already exists, inspect
`systemctl cat tailscaled.service` and reconcile its paths before replacing it;
do not run a second daemon against the same state.

## 4. Join the tailnet and enable Tailscale SSH

Still in your USB session on the **tablet**, run:

```bash
/home/root/tailscale/bin/tailscale up --ssh --hostname=remarkable-tablet
```

Open the displayed login URL on the computer and sign in to the same tailnet.
Confirm `remarkable-tablet` appears in Tailscale's **Machines** page and approve
it there if your tailnet requires device approval. Interactive browser login
avoids embedding an auth key in a command, service file, or shell history.

For an already joined tablet, change only the needed settings instead:

```bash
/home/root/tailscale/bin/tailscale set --ssh --hostname=remarkable-tablet
```

Then check on the **tablet**:

```bash
/home/root/tailscale/bin/tailscale status
/home/root/tailscale/bin/tailscale ip -4
```

Record your own `100.x.y.z` address. There is no need to advertise subnet routes,
an exit node, or a public Funnel. Tailscale SSH serves tailnet connections itself;
local Wi-Fi and USB connections continue to use Dropbear. Your Dropbear public
keys and root password do not authorize the Tailscale SSH connection.

## 5. Allow the connection in your tailnet policy

Tailscale SSH needs **both** network access to TCP 22 and an SSH policy permitting
your identity to log in as `root`. Edit **Access controls** in the Tailscale admin
console. The following is an example for an **untagged tablet owned by your user**.
Replace the email and example IP with your own. Merge it into your policy,
preserving other services' rules; do not replace a shared tailnet's entire policy.

```json
{
  "hosts": {
    "remarkable-tablet": "100.101.102.103"
  },
  "grants": [
    {
      "src": ["you@example.com"],
      "dst": ["remarkable-tablet"],
      "ip": ["tcp:22"]
    }
  ],
  "ssh": [
    {
      "action": "check",
      "checkPeriod": "12h",
      "src": ["you@example.com"],
      "dst": ["autogroup:self"],
      "users": ["root"]
    }
  ]
}
```

The network grant names only the tablet. `autogroup:self` in the SSH rule covers
devices owned by your identity; existing broad network grants can allow access
to other owned devices too. For a tagged tablet, use its dedicated tag as the
destination in both rules and configure tag ownership; `autogroup:self` does not
match tagged devices. Use the console's policy validation and tests before saving.
See Tailscale's [SSH policy documentation](https://tailscale.com/docs/features/tailscale-ssh)
and [grant examples](https://tailscale.com/docs/reference/examples/grants).

`check` may require browser reauthentication, which interrupts unattended
delivery. For scheduled sending, you can deliberately use `"action": "accept"`
and remove `checkPeriod` for the authorized identity. That trusts its existing
tailnet login without an additional SSH approval. Overlapping `check` rules take
precedence, so review the existing default rule too. Do not grant every tailnet
member root access just to make a scheduled job work.

## 6. Configure rmsend on the computer

Add this to the **computer's** `~/.ssh/config`, replacing the example address:

```sshconfig
Host remarkable
    HostName 100.101.102.103
    User root
    ConnectTimeout 10
```

You can use the tablet's [MagicDNS name](https://tailscale.com/docs/features/magicdns)
instead if MagicDNS is enabled on your computer. A numeric tailnet IP also works
when DNS is unavailable. Keep the
separate `remarkable-usb` and optional `remarkable-wifi` aliases from the setup
guide for recovery.

Tailscale SSH uses tailnet identity rather than `IdentityFile`. Its host key can
differ from Dropbear's USB/Wi-Fi key. On a computer with the
[Tailscale CLI](https://tailscale.com/docs/reference/tailscale-cli#ssh),
`tailscale ssh root@remarkable-tablet` verifies the SSH host key against the
coordination server's advertised key. Otherwise verify the fingerprint through
trusted device/admin information before accepting it with ordinary SSH. Do not
disable host-key checking or delete a changed-key warning without investigating.

Test a new connection from the **computer**, complete any browser check, and
then verify the noninteractive connection used by rmsend:

```bash
ssh remarkable true
ssh -o BatchMode=yes -o ControlPath=none remarkable true
rmsend examples/sample.html --transport ssh
```

The default alias is already `remarkable`. With another alias, use
`RMSEND_SSH_HOST=my-tablet rmsend file.pdf --transport ssh`. Save and close any
open notebook first: an SSH delivery restarts the tablet's `xochitl` UI.

## Firmware updates, reboots, and removal

The enabled service starts on normal boot. The tablet must still be awake with
working Wi-Fi; this service cannot keep a sleeping radio reachable. Check a
normal reboot when convenient, keeping a USB cable available for recovery.

Firmware updates can replace `/etc` and the service's enablement. Files under
`/home` usually persist, but that is not a guarantee or a backup. After an update,
use **USB SSH** to check the binary, private state directory, and service. If the
service disappeared, repeat step 3 using the saved copy at
`/home/root/tailscale/tailscaled.service`. Then check `tailscale status`; reuse the
existing state rather than overwriting it or registering a duplicate device.
Recheck local Wi-Fi SSH's marker/socket if you use that route too.

If the device's Tailscale key expires, reconnect over USB and run
`/home/root/tailscale/bin/tailscale up --force-reauth`, then complete browser login.
Keeping expiry enabled means occasionally doing this. Disabling expiry for a
trusted tablet in **Machines** supports unattended delivery but keeps its device
credential valid until revoked; remove/revoke a lost tablet promptly.
See [key expiry](https://tailscale.com/docs/features/access-control/key-expiry).

To stop Tailscale, use a **USB session**, since these commands cut tailnet access:

```bash
/home/root/tailscale/bin/tailscale logout
systemctl disable --now tailscaled.service
```

Remove the device from the Tailscale admin console. You can then remove the
service file and installation directory if desired; keep your USB public key
and tablet documents. Do not run logout or replace state just to troubleshoot a
temporary Wi-Fi outage.

## Troubleshooting

| Symptom | Check |
|---|---|
| Tablet offline | Wake it; verify Wi-Fi/internet and that the computer is signed into the same tailnet. |
| `Exec format error` | reMarkable 2 needs the `arm` archive, not `arm64` or `amd64`. |
| `/dev/net/tun` error | Inspect `systemctl cat tailscaled`; it must include `--tun=userspace-networking`. |
| Cannot connect to local tailscaled | On the tablet, check `systemctl is-active tailscaled` and the socket path in the service. |
| Service fails | Read `journalctl -u tailscaled -n 50 --no-pager` over USB; check executable paths, space, and `/home` permissions. Redact logs before sharing. |
| Tailnet reachable, SSH denied | Check `--ssh`, both policy sections, `root`, device ownership/tagging, and browser check-mode approval. |
| SSH times out | Check the tablet is awake, policy permits TCP 22, and incoming connections are not blocked by shields-up. If available, try `tailscale ping remarkable-tablet` on the computer. |
| MagicDNS name fails | Use the tablet's numeric Tailscale IP in `HostName`, or fix MagicDNS on the computer. |
| USB works, tailnet fails after update | Restore/enable the service from the copy on `/home`, then check login/key expiry. |
| SSH host key changed | Check whether the address now selects Tailscale SSH instead of Dropbear, or state was reset. Verify the new key before updating `known_hosts`. |
