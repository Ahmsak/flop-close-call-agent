# P1-C: local Devnet credential preparation

2026-11-02. Read docs/RUNBOOK.md first. This supplement grants no execution permission.
No SDK/CLI installed. No wallet, seed, faucet, challenge, enrollment or inference run.

## Actual CLI path

CLI 0.4.0 uses node:os homedir() + .flop. A harmless Node homedir probe under the
owner confirmed the intended Windows profile. Files expected there:
- devnet-enroll-wallet.json (plaintext sr25519 mnemonic)
- devnet-wallet-agent-key.json (plaintext bearer)
No custom credential directory flag was found in agent credential. Do not change HOME,
USERPROFILE or move existing Hermes/Technocore credentials to redirect it.

The previously absent .flop directory was created EMPTY. Owner: the intended Windows
user. Protected DACL: that user, SYSTEM and Administrators only, FullControl with
ObjectInherit/ContainerInherit. Ancestors and directory had no reparse points.
The configured OneDrive root is a sibling, not an ancestor. This does not exclude
unregistered third-party backup/sync software or an administrator reading files.

## Windows ACL gate — ordinary owner PowerShell, not automation sandbox

An intervening automation tool invocation added CodexSandboxUsers read access to the
new directory. A nonsecret probe detected inherited exposure. The probe was deleted;
the extra group was removed with targeted icacls, preserving SYSTEM/Administrators.
Final same-invocation directory and probe verification PASSED; the directory was empty.
An attempted full ACL replacement failed with SeSecurityPrivilege; targeted removal
succeeded. Do not assume permissions stay unchanged across automation calls.

Run this read-only gate immediately before AND after future creation from the intended
owner's ordinary PowerShell. It reads security descriptors and metadata, not secrets.
If it fails, STOP; no automatic permission repair or credential recreation.

```powershell
$ErrorActionPreference = 'Stop'
$root = Join-Path $env:USERPROFILE '.flop'
$ownerSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$allowed = @($ownerSid, 'S-1-5-18', 'S-1-5-32-544')
$cursor = Get-Item -LiteralPath $root -Force
while ($null -ne $cursor) {
    if ($cursor.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'Reparse ancestor: STOP'
    }
    $cursor = $cursor.Parent
}
$paths = @($root)
foreach ($name in @('devnet-enroll-wallet.json','devnet-wallet-agent-key.json')) {
    $path = Join-Path $root $name
    if (Test-Path -LiteralPath $path) { $paths += $path }
    else { Write-Output "$name ABSENT" }
}
foreach ($path in $paths) {
    $item = Get-Item -LiteralPath $path -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse file' }
    $acl = Get-Acl -LiteralPath $path
    $sid = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    if ($sid -ne $ownerSid) { throw 'Unexpected owner' }
    if ($path -eq $root -and -not $acl.AreAccessRulesProtected) { throw 'Parent inheritance open' }
    $seen = @()
    foreach ($rule in $acl.Access) {
        $sid = $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
        if ($sid -notin $allowed -or $rule.AccessControlType -ne 'Allow' -or
            $rule.FileSystemRights -ne [Security.AccessControl.FileSystemRights]::FullControl) {
            throw 'Unexpected ACL: STOP'
        }
        $seen += $sid
    }
    foreach ($sid in $allowed) { if ($sid -notin $seen) { throw 'Required principal missing' } }
    Write-Output "$($item.Name) ACL_PASS"
}
```

This checks the closed principal set and ownership; it is not an impersonation test
of SYSTEM/Administrators or protection against administrator privilege. Creation/read
and inheritance were tested as owner using a nonsecret file, then that file was removed.
Inspect effective access again if group membership or security tooling changes.
No secrets in command arguments, transcript, output, Git or diagnostic reports.
Do not use --print-key. CLI mode 0600 alone is insufficient on Windows. Use encrypted
backup outside cloud sync; stock CLI cannot directly read DPAPI ciphertext.

## Time and network observations

Windows timezone: Central Asia Standard Time, UTC+06, Bishkek. Session timezone is
Asia/Almaty (UTC+05). W32Time is Disabled/Stopped; w32tm reported service not started.
No time/service settings changed.

Gateway GET /v1/models: local end 2026-11-02T04:39:02.754600Z;
HTTP Date 2026-11-02T05:40:05Z (server +3662.25 seconds).
Docs GET /networks/devnet: local end 04:39:03.128549Z;
HTTP Date 05:40:05Z (server +3661.87 seconds), Cache-Control no-store.
Gateway CF-Cache-Status DYNAMIC, Age absent; price chain:2693340 effective
05:39:55.001Z, expires 05:41:55.001Z. Price is current against HTTP Date but future
against local UTC. Earlier price version changed. Evidence favors a clock discrepancy,
not timezone conversion or a stale price cache. Which clock is correct remains UNKNOWN:
the two official HTTP hosts are not independent trusted time authorities. Do not silently
apply an offset or relax stale/future-price guards. Independent time validation required.

One read-only WSS call to wss://rpc.devnet.flop.network, chain_getBlockHash([0]), returned:
0x99c172c095340ace980631f9123544c6bebd4839f3437e463533422d8be2d631
No subscription, transaction or HTTP POST. This is an OBSERVED genesis, not a pinned
independent trust anchor. Require independently published/operator-authenticated network
identity before funding or signing. No faucet endpoint was contacted in P1-C.

## Future owner procedure — NOT authorized by P1-C

1. Obtain independent network identity and resolve UTC discrepancy; verify catalog price.
2. Re-run ACL gate from ordinary owner PowerShell; directory must remain empty or existing
   files must be accounted for. Never overwrite an existing wallet or bearer.
3. Separately approve pinned CLI installation/dependencies and local test wallet creation.
4. Separately approve faucet, challenge signature and enrollment. The official command
   `flop --network devnet agent credential --json` bundles these side effects and may reuse
   or rotate cached credentials; it is NOT a read-only command. Do not execute it while
   only local wallet creation is authorized. Its automatic funding path lacks the separate
   faucet/RPC genesis precheck discussed in P1-B.
5. Immediately recheck ACL of generated files and temporary-file location. If unexpected
   access appears, stop and assess exposure; don't delete history or regenerate silently.
6. Inspect credential metadata through keys/me without logging bearer. Require model scope,
   expiry and hard test-only quota. No real-money funding, no mainnet fallback.
7. Inference needs separate approval, verified price/budget and a live Durable transport.
   Until then EXECUTION_DISABLED remains. No cron, Hermes launch or delivery.

Rollback: only remove this newly created directory nonrecursively if it is still empty,
from ordinary owner PowerShell. Never recursively remove .flop or any future credential.
Existing keys were not opened, copied, hashed or modified. No operational installation,
SQLite, permissions policy or launcher changed. No commit/push.
