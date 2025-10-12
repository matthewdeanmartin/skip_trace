# skip_trace/reporting/md_reporter.py
from __future__ import annotations

import sys
from typing import IO

from rich.console import Console
from rich.table import Table

from ..schemas import EvidenceKind, EvidenceSource, PackageResult


def render(result: PackageResult, file: IO[str] = sys.stdout):
    """
    Renders the PackageResult as a rich report to the console.

    Args:
        result: The PackageResult object to render.
        file: The file object to write to (defaults to stdout).
    """
    import shutil

    width, _ = shutil.get_terminal_size((80, 175))
    console = Console(file=file, width=width)
    version_str = f" v{result.version}" if result.version else ""
    console.print(
        f"\n[bold]📦 skip-trace: Ownership Report for {result.package}{version_str}[/bold]"
    )
    console.print("-" * 80)

    # --- Pre-process to find Sigstore evidence ---
    sigstore_evidence = [
        ev for ev in result.evidence if ev.source == EvidenceSource.SIGSTORE
    ]
    sigstore_evidence_ids = {ev.id for ev in sigstore_evidence}

    # --- OWNERS TABLE ---
    if not result.owners:
        console.print("\n[bold]## 🕵️ Owner Candidates[/bold]")
        console.print("\nNo owner candidates found.\n")
    else:
        console.print("\n[bold]## 🕵️ Owner Candidates[/bold]")
        # Create a lookup map for evidence for fast access
        evidence_map = {ev.id: ev for ev in result.evidence}

        owner_table = Table(
            show_header=True,
            header_style="bold magenta",
            title="Top Owner Candidates (by inferred score)",
            title_style="bold",
        )
        owner_table.add_column("Owner", style="cyan", width=30, no_wrap=True)
        owner_table.add_column("Kind", width=10)
        owner_table.add_column("Score", justify="right", style="bold")
        owner_table.add_column("Contacts", width=65)
        owner_table.add_column("Key Evidence Notes", no_wrap=False)

        for owner in result.owners:
            score_str = f"{owner.score:.2f}"
            score_style = (
                "green"
                if owner.score >= 0.7
                else "yellow" if owner.score >= 0.5 else "red"
            )

            contact_parts = []
            for contact in owner.contacts:
                value = contact.value
                if contact.type.value in ("url", "repo") and len(value) > 60:
                    value = value[:60] + "..."
                contact_parts.append(f"[bold dim]{contact.type.value}[/]: {value}")
            contacts_str = (
                "\n".join(contact_parts)
                if contact_parts
                else "[italic]None found[/italic]"
            )

            # Look up the notes from the evidence IDs
            evidence_notes = []
            for ev_id in owner.evidence:
                evidence_record = evidence_map.get(ev_id)
                if evidence_record and evidence_record.notes:
                    evidence_notes.append(f"• {evidence_record.notes}")
            key_evidence_str = (
                "\n".join(evidence_notes)
                if evidence_notes
                else "[italic]No notes.[/italic]"
            )

            # Check if this owner is backed by Sigstore evidence
            is_verified = bool(sigstore_evidence_ids.intersection(owner.evidence))
            owner_display_name = f"🛡️ {owner.name}" if is_verified else owner.name

            owner_table.add_row(
                owner_display_name,
                owner.kind.value,
                f"[{score_style}]{score_str}[/]",
                contacts_str,
                key_evidence_str,
            )
        console.print(owner_table)
        console.print(
            "[dim]Owners marked with 🛡️ are supported by cryptographic evidence.[/dim]"
        )

    # --- CRYPTOGRAPHIC EVIDENCE (SIGSTORE) ---
    if sigstore_evidence:
        console.print("\n[bold]## 🛡️ Cryptographic Evidence (from Sigstore)[/bold]")
        sig_table = Table(
            show_header=True,
            header_style="bold green",
            title="Verified Signatures and Provenance",
            title_style="bold",
        )
        sig_table.add_column("Kind", style="cyan", width=25)
        sig_table.add_column("Identity or Source")
        sig_table.add_column("Notes")

        for ev in sigstore_evidence:
            kind_str = ev.kind.value.replace("sigstore-", "").replace("-", " ").title()
            primary_value = ""
            if ev.kind == EvidenceKind.SIGSTORE_SIGNER_IDENTITY:
                primary_value = ev.value.get("identity", "[unknown]")
            elif ev.kind == EvidenceKind.SIGSTORE_BUILD_PROVENANCE:
                primary_value = ev.value.get("repo_uri", "[unknown]")

            sig_table.add_row(kind_str, primary_value, ev.notes)
        console.print(sig_table)

    # --- MAINTAINERS TABLE ---
    if result.maintainers:
        console.print("\n[bold]## 🧑‍💻 PyPI Maintainers[/bold]")
        maintainer_table = Table(
            show_header=True,
            header_style="bold cyan",
            title="Directly Listed Maintainers (from PyPI)",
            title_style="bold",
        )
        maintainer_table.add_column("Name", style="cyan")
        maintainer_table.add_column("Email")
        maintainer_table.add_column("Confidence", justify="right")

        for maintainer in sorted(
            result.maintainers, key=lambda m: m.confidence, reverse=True
        ):
            email_str = maintainer.email or "[italic]Not provided[/italic]"
            confidence_str = f"{maintainer.confidence:.2f}"
            maintainer_table.add_row(maintainer.name, email_str, confidence_str)

        console.print(maintainer_table)

    # --- URL STATUS TABLE ---
    url_status_evidence = [
        ev for ev in result.evidence if ev.kind == EvidenceKind.URL_STATUS
    ]
    if url_status_evidence:
        console.print("\n[bold]## 🔗 URL Analysis[/bold]")
        url_table = Table(
            show_header=True, header_style="bold blue", title="Checked URLs"
        )
        url_table.add_column("URL", style="cyan", no_wrap=True)
        url_table.add_column("HTTP Status", justify="center")

        for ev in sorted(url_status_evidence, key=lambda x: x.locator):
            status = ev.value.get("status_code", "N/A")
            status_str = str(status)
            if status == -1:
                status_str = "Connection Error"
                style = "bold red"
            elif 200 <= status < 300:
                style = "green"
            elif 300 <= status < 400:
                style = "yellow"
            else:
                style = "red"
            url_table.add_row(ev.locator, f"[{style}]{status_str}[/]")
        console.print(url_table)

    console.print("-" * 80)
