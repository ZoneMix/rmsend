# Device setup

## Computer prerequisites

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), Chrome or
Chromium for PDF output, and optionally pandoc for EPUB. You need OpenSSH's `ssh`
command for SSH delivery. No Python environment needs to be activated: rmsend
uses uv's inline dependency metadata and checked-in script lockfile.

On macOS with Homebrew:

```bash
brew install uv pandoc
brew install --cask google-chrome
```

On Debian/Ubuntu, install Chromium, pandoc, and the OpenSSH client through your
distribution, then install uv using its official instructions. The executable
looks for Chrome/Chromium/Edge in their standard macOS application paths, then
`chromium`, `chromium-browser`, `google-chrome`, `google-chrome-stable`, or `chrome`
on PATH. PDF output requires a working graphical browser in headless mode.
When both are installed, system Google Chrome is preferred. Some Ubuntu
Chromium builds cannot start their sandbox under AppArmor's user-namespace
restrictions. Install system Chrome or configure your distribution's supported
Chromium sandbox; rmsend does not disable the sandbox. See the
[Chromium explanation](https://chromium.googlesource.com/chromium/src/+/main/docs/security/apparmor-userns-restrictions.md).

## USB web interface: simplest route

1. Connect a USB cable that supports data, not just charging.
2. Wake the tablet. Enable the USB web interface in Settings → General settings
   → Storage. Menu wording can vary with firmware.
3. Open `http://10.11.99.1` on the connected computer. If you cannot reach it,
   fix the cable/device connection first.
4. Run `rmsend file.pdf --transport web`.

USB transfers do not need a password, SSH keys, or a UI restart. The web interface
places uploads in the tablet library; folder selection and retention require SSH.
Firmware may turn the interface off after disconnecting the cable.

The vendor documents USB import, supported formats, and its current transfer
limit in [Importing and exporting files](https://support.remarkable.com/articles/Knowledge/importing-and-exporting-files).
For larger documents, divide the source file before transfer or use SSH.

## SSH over USB: bootstrap and recovery

This project has been used with reMarkable 2. Obtain your own tablet's SSH/root
password and address from its About/Help/Copyright-and-licenses settings; consult
[reMarkable's developer portal](https://developer.remarkable.com/) for your model.
Paper Pro models have different developer-mode requirements and are untested
here. Start with USB's `10.11.99.1`. Keep this connection available while setting
up wireless access; it is also the recovery route if Tailscale stops working.
The USB web-interface toggle controls document uploads, not SSH authentication.

First verify interactive access:

```bash
ssh root@10.11.99.1
```

Check the first connection's host-key fingerprint through a trusted connection
or on the device; accepting an unverified key does not verify the device. The
tablet's Dropbear server can display its public host key and fingerprint with
`dropbearkey -y -f /etc/dropbear/dropbear_ed25519_host_key` on the tested firmware.
Exit that session, generate a dedicated key if you do not have one, and install
the public key. Choose a passphrase; do not overwrite an existing key.
`ssh-copy-id` will ask for the tablet password interactively:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/remarkable -C rmsend
ssh-copy-id -i ~/.ssh/remarkable.pub root@10.11.99.1
ssh-add ~/.ssh/remarkable
```

On macOS, `brew install ssh-copy-id` provides that command. Alternatively, append
the public key over your verified USB SSH connection:

```bash
ssh root@10.11.99.1 'umask 077; mkdir -p /home/root/.ssh; cat >> /home/root/.ssh/authorized_keys; chmod 700 /home/root/.ssh; chmod 600 /home/root/.ssh/authorized_keys' < ~/.ssh/remarkable.pub
```

Never put the private key on the tablet. For a passphrase-protected key,
`ssh-add` unlocks it for the current agent session; an unattended job needs a
running agent with the key already loaded. Ordinary Ed25519 keys work with the
tested Dropbear server. Hardware-backed `ed25519-sk` keys require server support
and should not be assumed to work with the tablet's bundled SSH server.

Add this entry to your computer's `~/.ssh/config`, using your own address:

```sshconfig
Host remarkable-usb
    HostName 10.11.99.1
    User root
    IdentityFile ~/.ssh/remarkable
    IdentitiesOnly yes
```

Then verify the noninteractive access rmsend requires:

```bash
ssh -o BatchMode=yes remarkable-usb true
RMSEND_SSH_HOST=remarkable-usb rmsend file.pdf --transport ssh
```

## SSH over local Wi-Fi

Join a Wi-Fi network using the tablet's settings. Put the computer on a network
that can reach the tablet; guest Wi-Fi isolation and VLAN rules can prevent this.
Read the tablet's current Wi-Fi IP in its settings or your router's DHCP leases.
A DHCP reservation keeps the address stable.

Firmware may require opting in to Wi-Fi SSH. On the tested reMarkable 2 running
**3.28.0.172**, the `dropbear-wlan.socket` unit checks for this marker. From your
USB SSH session, inspect that unit first:

```bash
systemctl cat dropbear-wlan.socket
```

If it includes `ConditionPathExists=/home/root/.config/remarkable/rm_enable_ssh_wifi_marker`,
enable it on the **tablet** with:

```bash
mkdir -p /home/root/.config/remarkable
touch /home/root/.config/remarkable/rm_enable_ssh_wifi_marker
systemctl restart dropbear-wlan.socket
systemctl is-active dropbear-wlan.socket
```

Expect `active`. Other firmware may provide an SSH setting in the tablet UI or
use different units; follow that firmware's mechanism instead of inventing a
replacement listener. A managed device's `rm_disable_ssh` restriction must be
handled by its administrator. Enabling Wi-Fi SSH exposes the root login to
devices that can reach the tablet's local network. It is optional for the
Tailscale SSH setup below, and you can leave it off if you only need tailnet SSH.

On your **computer**, add a separate alias to `~/.ssh/config`. Replace the example
address with your tablet's Wi-Fi address; use the same key installed over USB:

```sshconfig
Host remarkable-wifi
    HostName 192.168.1.50
    User root
    IdentityFile ~/.ssh/remarkable
    IdentitiesOnly yes
    ConnectTimeout 10
```

Verify the host key against the USB connection, then test and send:

```bash
ssh remarkable-wifi true
ssh -o BatchMode=yes remarkable-wifi true
RMSEND_SSH_HOST=remarkable-wifi rmsend file.pdf --transport ssh
```

To turn local Wi-Fi SSH off on the tested firmware, run these on the **tablet**:

```bash
rm -f /home/root/.config/remarkable/rm_enable_ssh_wifi_marker
systemctl stop dropbear-wlan.socket
```

## SSH over Tailscale: wireless delivery away from home

Follow [the complete Tailscale guide](tailscale.md) to reproduce the maintainer's
setup: ARM static binaries on the tablet, userspace networking, a systemd service,
Tailscale SSH, and a `remarkable` alias on the computer. It includes tailnet
permissions, firmware-update recovery, and troubleshooting. No router port
forwarding, reMarkable cloud account, or custom kernel is needed.

Tailscale SSH authenticates your tailnet identity and its SSH policy. USB and
local Wi-Fi SSH use the tablet's own Dropbear server and your installed public
key. These are separate authentication paths and can have different host keys.
Installing a key over USB alone does not grant Tailscale SSH access.

The computer and tablet must both be connected to the same tailnet. Wake the
tablet and give Wi-Fi time to reconnect; sleep can turn its Wi-Fi off. rmsend
does not wake a sleeping tablet, install Tailscale, or establish the VPN itself.

Alternatively, choose another alias without editing rmsend:

```bash
RMSEND_SSH_HOST=my-tablet rmsend file.pdf --transport ssh
```

SSH installs the PDF/EPUB plus `.metadata` and `.content` sidecars under
`/home/root/.local/share/remarkable/xochitl/`, then restarts `xochitl` once. This
relaunches the tablet UI. Save and close your current notebook first. Folder
operations and retention use the same SSH connection. Firmware upgrades can
change these internal file formats; back up valuable annotations before using
third-party tools on a new firmware version.

## Troubleshooting

| Symptom | Check |
|---|---|
| `uv: command not found` | Install uv and check your PATH. |
| No Chrome/Chromium found | Install a supported browser, or use `--format epub` with pandoc. |
| No reMarkable found | Wake it; verify USB's web interface or `ssh -o BatchMode=yes remarkable true`. |
| SSH permission denied | Check `User root`, public-key installation, and `ssh-add` for a passphrase-protected key. |
| USB SSH works, Wi-Fi SSH does not | Check the Wi-Fi opt-in marker/socket, address, and network isolation. |
| Tailscale connects but SSH fails | Check both the network grant and Tailscale SSH rule; see [tailscale.md](tailscale.md). |
| SSH host key changed | Verify the new fingerprint on the tablet; do not disable host-key checking. |
| No folder named … | Make it in the tablet library or pass `--create-folder`. |
| Uploaded document invisible | Wait for the library redraw; with `--no-restart`, restart xochitl yourself. |
| PDF text differs between computers | Compare installed fonts and browser versions; see [design.md](design.md). |
| Mere Orthodoxy refuses export | Read the specific schema/format error; [supported formats](mere-orthodoxy.md). |
