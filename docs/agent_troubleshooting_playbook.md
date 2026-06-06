# Agent Troubleshooting Playbook

This playbook captures safe, general troubleshooting patterns for the SSH planning agent. It is not a list of hidden incidents or hardcoded fixes. Use it to propose better one-command-at-a-time actions with less technician correction.

## Core Behavior

- Propose exactly one command per step.
- Prefer diagnosis before fixes.
- Use the most recent observations; do not repeat a command that already answered the same question.
- Prefer read-only commands without `sudo` when they provide enough evidence.
- Use `sudo -n` only for targeted commands that truly need privileges, so commands fail fast instead of prompting.
- Avoid broad status dumps, broad filesystem scans, package installs, blanket permission changes, data deletion, log clearing, and secret reads.
- When using shell composition, keep it minimal and explain why the composition is needed.

## Linux Service Incidents

- If a customer endpoint is unreachable, first check whether the expected port is listening.
- If no listener exists, identify the relevant service with targeted systemd unit inspection.
- Check service boot persistence and runtime state separately when possible.
- Inspect the unit file with `systemctl cat <service>` before changing it.
- Inspect recent service logs with `journalctl -u <service> -n <count> --no-pager` to find the technical cause.
- If a unit uses an environment file, inspect only the relevant non-secret keys such as `PORT`, `HOST`, or service-specific public settings. Do not dump full env files.
- If the service is disabled but should persist after reboot, propose `sudo -n systemctl enable <service>` separately from starting it.
- If a config value is wrong, propose the smallest targeted edit and then a proportional service restart.

## Validation

- Validate customer benefit directly, for example with the endpoint from the ticket.
- Validate persistence when relevant by checking enabled state, restart behavior, or the provided public test.
- Prefer commands with bounded timeouts for HTTP checks, such as `curl --max-time 5 -fsS ...`.
- Run the provided public validation script only after direct evidence indicates the fix is likely correct.
- Validation evidence must be concrete: command, exit code, and successful output.
