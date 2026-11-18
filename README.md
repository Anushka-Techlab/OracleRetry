# orecle-retry

Retries an existing Oracle Cloud Infrastructure (OCI) Resource Manager stack until an apply succeeds. GitHub hosts the runner, so your computer can be offline.

## Setup

1. Use a dedicated Resource Manager stack configured to create the VM you want. The original stack used Ubuntu 24.04 ARM64 on VM.Standard.A1.Flex in Mumbai with 4 OCPUs, 24 GB RAM and a 200 GB boot volume. Shape, networking, SSH access and disk settings come from your stack. Each apply automatically approves its Terraform changes.
2. Create a personal GitHub repository with Issues and Actions enabled and default branch `main`. Add the six repository secrets below under **Settings → Secrets and variables → Actions**. Use a fresh OCI API signing key if the previous one was shared.
3. Push the contents of this folder to the root of `main`, including `.github`. The push starts the first run. You can also select **Actions → retry-oci-instance → Run workflow**.
4. Read the attempt timestamps in the workflow summary. Check the Oracle Resource Manager job log for the cause of a failed apply. On success, the workflow opens an issue, assigns it to the repository owner and mentions them. Email delivery follows that user's GitHub notification settings.

| Repository secret | Value |
| --- | --- |
| OCI_CLI_USER | OCID of the Oracle API user |
| OCI_CLI_TENANCY | Tenancy OCID |
| OCI_CLI_FINGERPRINT | Fingerprint of the registered API signing key |
| OCI_CLI_REGION | Region containing the stack, such as ap-mumbai-1 |
| OCI_CLI_KEY_CONTENT | Full unencrypted RSA private signing key in PEM format |
| OCI_STACK_ID | OCID of the existing Resource Manager stack |

The Oracle user needs access to list, read and create Resource Manager jobs on the stack. The GitHub workflow token needs Actions and Issues write access.

## Retry behavior

- A failed apply waits 10 minutes before another attempt. An Oracle API rate limit waits 15 minutes. Other CLI errors, including authentication errors, fail the run and stop self-dispatch.
- Each run has a 5½-hour retry window. At the deadline it dispatches the next run. A 30-minute cron trigger provides a backup. Concurrency permits one active run at a time.
- A replacement runner checks for outstanding jobs before submitting an apply. Any successful apply in the stack's history stops provisioning, even if the VM is later removed. A previously created notification issue is reused.
- A failed Terraform apply can have causes other than capacity. Inspect persistent failures in Oracle. To stop retries and scheduled checks, disable the workflow in GitHub Actions and cancel any active run. A submitted Oracle job has its own lifecycle.
