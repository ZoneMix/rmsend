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

## SSH over USB or Wi-Fi

This project has been used with reMarkable 2. Obtain your own tablet's SSH/root
password and address from its About/Help/Copyright-and-licenses settings; consult
[reMarkable's developer portal](https://developer.remarkable.com/) for your model.
Paper Pro models have different developer-mode requirements and are untested
here. Start with USB's `10.11.99.1`, or use the tablet's own Wi-Fi address.

First verify interactive access:

```bash
ssh root@10.11.99.1
```

Verify the displayed host-key fingerprint before accepting a new host. Exit
that session, generate a dedicated key if you do not have one, and install the
public key. `ssh-copy-id` will ask for the tablet password interactively:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/remarkable -C rmsend
ssh-copy-id -i ~/.ssh/remarkable.pub root@10.11.99.1
ssh-add ~/.ssh/remarkable
```

If your OpenSSH install lacks `ssh-copy-id`, install the OpenSSH tools or append
the public key to the tablet's `/home/root/.ssh/authorized_keys` using your usual
SSH administration workflow. Never put the private key on the tablet.

Add this entry to your computer's `~/.ssh/config`, using your own address:

```sshconfig
Host remarkable
    HostName 10.11.99.1
    User root
    IdentityFile ~/.ssh/remarkable
    IdentitiesOnly yes
```

Then verify the noninteractive access rmsend requires:

```bash
ssh -o BatchMode=yes remarkable true
rmsend file.pdf --transport ssh
```

For wireless delivery, change `HostName` to your tablet's reachable Wi-Fi address.
An existing Tailscale/VPN route can be used in the same way. Tailscale is optional;
this project does not install software on the tablet or establish a VPN. You
do not need remote access for USB delivery. Keep the tablet awake: its Wi-Fi may
turn off while sleeping.

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
| SSH host key changed | Verify the new fingerprint on the tablet; do not disable host-key checking. |
| No folder named … | Make it in the tablet library or pass `--create-folder`. |
| Uploaded document invisible | Wait for the library redraw; with `--no-restart`, restart xochitl yourself. |
| PDF text differs between computers | Compare installed fonts and browser versions; see [design.md](design.md). |
| Mere Orthodoxy refuses export | Read the specific schema/format error; [supported formats](mere-orthodoxy.md). |
