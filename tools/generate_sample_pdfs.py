from pathlib import Path
import textwrap


ROOT = Path(__file__).resolve().parents[1] / "data" / "sample_data"
PAGE_WIDTH = 612
PAGE_HEIGHT = 792
LEFT = 54
TOP = 738
LINE_HEIGHT = 14
FONT_SIZE = 10
LINES_PER_PAGE = 48


def pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(pages: list[list[str]]) -> bytes:
    objects: list[bytes] = []

    def add_object(data: bytes) -> int:
        objects.append(data)
        return len(objects)

    font_id = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    content_ids: list[int] = []
    page_ids: list[int] = []

    for lines in pages:
        stream_lines = [b"BT", f"/F1 {FONT_SIZE} Tf".encode(), f"1 0 0 1 {LEFT} {TOP} Tm".encode()]
        for idx, line in enumerate(lines):
            if idx > 0:
                stream_lines.append(f"0 -{LINE_HEIGHT} Td".encode())
            stream_lines.append(f"({pdf_escape(line)}) Tj".encode())
        stream_lines.append(b"ET")
        stream = b"\n".join(stream_lines)
        content_ids.append(add_object(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"))

    pages_root_id = add_object(b"")
    for content_id in content_ids:
        page_ids.append(
            add_object(
                (
                    f"<< /Type /Page /Parent {pages_root_id} 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                    f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
                ).encode()
            )
        )

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[pages_root_id - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()
    catalog_id = add_object(f"<< /Type /Catalog /Pages {pages_root_id} 0 R >>".encode())

    result = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(result))
        result.extend(f"{i} 0 obj\n".encode())
        result.extend(obj)
        result.extend(b"\nendobj\n")
    xref_pos = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    result.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        result.extend(f"{off:010d} 00000 n \n".encode())
    result.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    )
    return bytes(result)


def wrap(text: str, width: int = 94) -> list[str]:
    return textwrap.wrap(" ".join(text.split()), width=width) if text else [""]


def bullets(items: list[str]) -> list[str]:
    lines: list[str] = []
    for item in items:
        lines.extend(wrap(f"- {item}"))
    lines.append("")
    return lines


def paragraph_block(paragraphs: list[str]) -> list[str]:
    lines: list[str] = []
    for para in paragraphs:
        lines.extend(wrap(para))
        lines.append("")
    return lines


def section(title: str, paragraphs: list[str] | None = None, bullet_items: list[str] | None = None) -> list[str]:
    lines = [title.upper(), ""]
    if paragraphs:
        lines.extend(paragraph_block(paragraphs))
    if bullet_items:
        lines.extend(bullets(bullet_items))
    return lines


def tabular_lines(rows: list[tuple[str, str]]) -> list[str]:
    lines: list[str] = []
    for left, right in rows:
        lines.extend(wrap(f"{left}: {right}"))
    lines.append("")
    return lines


def paginate(
    title: str,
    category: str,
    metadata_rows: list[tuple[str, str]],
    section_blocks: list[list[str]],
    minimum_pages: int = 10,
) -> list[list[str]]:
    lines = [title, f"Category: {category}", "Synthetic sample document for public portfolio review.", ""]
    lines.append("DOCUMENT CONTROL")
    lines.append("")
    lines.extend(tabular_lines(metadata_rows))
    for block in section_blocks:
        lines.extend(block)

    pages: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        current.append(line)
        if len(current) >= LINES_PER_PAGE:
            pages.append(current)
            current = []
    if current:
        pages.append(current)

    page_no = 1
    while len(pages) < minimum_pages:
        filler = [f"{title} - Appendix {page_no}", ""]
        filler.extend(
            section(
                f"Appendix {page_no}: Reference Notes",
                paragraphs=[
                    "This appendix page extends the fictional source material with supporting examples, logging expectations, and exception notes so later retrieval tests can traverse a longer document without relying on private or derived content.",
                    "Examples on appendix pages are intentionally consistent with the body of the document. They repeat the same operating vocabulary but add different details such as timings, thresholds, role ownership, and escalation triggers.",
                ],
                bullet_items=[
                    "Record location code, equipment identifier, shift, and operator initials on each manual intervention.",
                    "If a procedure references a tolerance band, use the tolerance from the most recent approved revision rather than memory or verbal guidance.",
                    "If a required part is unavailable, tag the task as deferred and note the risk to continued operation in the maintenance or service log.",
                    "For training simulations, supervisors may role-play escalation decisions, but the written record should still reflect the documented path in this guide.",
                ],
            )
        )
        pages.append(filler[:LINES_PER_PAGE])
        page_no += 1
    return pages


def maintenance_doc(
    title: str,
    doc_id: str,
    summary: str,
    tools: list[str],
    hazards: list[str],
    prep: list[str],
    steps: list[str],
    criteria: list[str],
    records: list[str],
    notes: list[str] | None = None,
) -> tuple[list[tuple[str, str]], list[list[str]]]:
    metadata = [
        ("Document ID", doc_id),
        ("Revision", "Rev 1.0"),
        ("Owner", "Facilities Reliability Team"),
        ("Applies To", "North Campus Distribution Operations"),
        ("Review Cycle", "Every 12 months or after equipment redesign"),
    ]
    sections = [
        section("Purpose", paragraphs=[summary, "The procedure is intended for trained maintenance technicians and shift leads. Production operators may assist with observation and restart confirmation, but they do not perform isolated service work unless the task card explicitly allows it."]),
        section("Required Tools and Parts", bullet_items=tools),
        section("Hazards and Controls", bullet_items=hazards),
        section("Preparation", bullet_items=prep),
        section("Procedure", bullet_items=steps),
        section("Acceptance Criteria", bullet_items=criteria),
        section("Records and Closeout", bullet_items=records),
        section("Examples and Notes", paragraphs=notes or []),
    ]
    return metadata, sections


def policy_doc(
    title: str,
    doc_id: str,
    scope: str,
    definitions: list[str],
    requirements: list[str],
    prohibited: list[str],
    exceptions: list[str],
    oversight: list[str],
) -> tuple[list[tuple[str, str]], list[list[str]]]:
    metadata = [
        ("Policy ID", doc_id),
        ("Revision", "Rev 1.0"),
        ("Owner", "Operations Governance Office"),
        ("Audience", "All employees, contractors, and project contributors"),
        ("Review Cycle", "Every 12 months or after a control failure"),
    ]
    sections = [
        section("Policy Statement", paragraphs=[scope]),
        section("Definitions", bullet_items=definitions),
        section("Requirements", bullet_items=requirements),
        section("Prohibited Practices", bullet_items=prohibited),
        section("Exceptions and Escalation", bullet_items=exceptions),
        section("Oversight and Enforcement", bullet_items=oversight),
        section(
            "Implementation Notes",
            paragraphs=[
                "Teams implementing this policy should translate the requirements into checklists, approval forms, and repository controls that are easy to audit. Local convenience does not override documented retention, redaction, or access requirements.",
                "Where two rules appear to conflict, the stricter public-release rule governs until the policy owner publishes a written exception or clarifying revision.",
            ],
        ),
    ]
    return metadata, sections


def troubleshooting_doc(
    title: str,
    doc_id: str,
    overview: str,
    symptoms: list[str],
    likely_causes: list[str],
    diagnostics: list[str],
    recovery: list[str],
    escalation: list[str],
    notes: list[str] | None = None,
) -> tuple[list[tuple[str, str]], list[list[str]]]:
    metadata = [
        ("Guide ID", doc_id),
        ("Revision", "Rev 1.0"),
        ("Owner", "Service Desk and Site Support"),
        ("Use Case", "Frontline diagnosis before depot repair or infrastructure escalation"),
        ("Review Cycle", "Every 6 months or after repeat incidents"),
    ]
    sections = [
        section("Overview", paragraphs=[overview]),
        section("Common Symptoms", bullet_items=symptoms),
        section("Likely Causes", bullet_items=likely_causes),
        section("Diagnostic Workflow", bullet_items=diagnostics),
        section("Recovery Actions", bullet_items=recovery),
        section("Escalation Criteria", bullet_items=escalation),
        section("Field Notes", paragraphs=notes or []),
    ]
    return metadata, sections


def build_documents() -> list[tuple[str, str, list[tuple[str, str]], list[list[str]]]]:
    docs = []
    docs.append(
        (
            "maintenance_procedures",
            "MP-01 Conveyor Belt Preventive Maintenance.pdf",
            *maintenance_doc(
                "MP-01 Conveyor Belt Preventive Maintenance",
                "MP-01-CNV-220",
                "This procedure defines the monthly preventive maintenance routine for the fictional CNV-220 takeaway conveyor used in the packing mezzanine. The goal is to catch belt tracking drift, worn rollers, loose guards, and overheating drive components before they interrupt outbound volume.",
                [
                    "Lockout kit with personal lock, hasp, and danger tag.",
                    "Infrared thermometer, 6 mm hex key set, belt tension gauge, flashlight, clean lint-free cloths.",
                    "Approved replacement hardware for side guards, nose pulley fasteners, and three standard return rollers.",
                    "Work order printout or digital task card showing the exact conveyor zone and last completed service date.",
                ],
                [
                    "Treat the conveyor as energized until lockout is verified at the local disconnect and start button.",
                    "Keep both side guards installed unless a specific inspection step calls for temporary removal and reinstall them before manual jogging.",
                    "Do not place hands between the belt and roller bed while checking tracking; use a marked reference point and observe from the frame edge.",
                    "If product debris contains broken glass, use cut-resistant gloves and dispose of waste in the designated rigid container.",
                ],
                [
                    "Confirm the service window with the area lead and post a maintenance in progress sign at both feeder points.",
                    "Stop the conveyor from the local HMI, isolate the disconnect, apply personal lockout, and test the start station for zero response.",
                    "Walk the full conveyor length and inspect belt edges, splice condition, side guides, frame welds, and return roller rotation.",
                    "Clean the nose pulley, tail pulley, photo-eye brackets, and debris traps. Note any product residue that could change tracking or sensor performance.",
                    "Measure motor surface temperature and gearbox housing temperature before adjustment. Compare readings to the baseline values in the task card.",
                    "Check belt tracking by hand-jogging only after all guards are temporarily reinstalled and the area is clear. If the belt drifts more than 5 mm at either edge, adjust the tail tracking bolts in quarter-turn increments.",
                    "Verify roller condition by spinning each return roller. Replace any roller that binds, chatters, or has visible flat spots.",
                    "Re-tension the belt only if the gauge reading falls outside the approved operating band of 32 to 36 units.",
                    "Restore the system, remove lockout, run the conveyor empty for three minutes, then run ten sample cartons through the full path.",
                ],
                [
                    "Belt tracks within 5 mm of centerline at empty and loaded conditions.",
                    "No exposed hardware, missing guards, or loose brackets remain after service.",
                    "Motor and gearbox temperatures are stable and do not exceed the prior baseline by more than 8 C.",
                    "Ten sample cartons pass without skewing, snagging, or photo-eye interruption faults.",
                ],
                [
                    "Record as-found and as-left belt tension readings in the work order.",
                    "List every adjusted component, replaced roller, and reused spare part by quantity.",
                    "If a defect is deferred, create a follow-up corrective work order and note the risk to throughput.",
                    "Obtain shift lead sign-off after the loaded restart test is complete.",
                ],
                [
                    "A common failure pattern on this fictional conveyor is gradual drift toward the operator side after two weeks of heavy carton volume. In past simulations, the root cause was usually tail roller contamination rather than major frame damage.",
                    "Technicians should avoid overcorrecting tracking with large bolt turns. Small adjustments followed by an empty run and a loaded run give more repeatable results and make later troubleshooting easier.",
                    "When reviewing the service log, compare temperature data by season. Ambient heat on the mezzanine can raise baseline readings in summer without indicating a drive failure.",
                ],
            ),
        )
    )
    docs.append(
        (
            "maintenance_procedures",
            "MP-02 Forklift Battery Bay Service Procedure.pdf",
            *maintenance_doc(
                "MP-02 Forklift Battery Bay Service Procedure",
                "MP-02-FLT-E18",
                "This procedure covers weekly inspection and light service of the fictional E18 electric forklift battery bay. It focuses on cable condition, connector heat, hold-down hardware, residue cleanup, and ventilation path integrity.",
                [
                    "Insulated hand tools, terminal brush, neutral cleaning solution, absorbent pads, inspection mirror, and torque wrench.",
                    "Replacement vent caps, cable ties rated for battery compartments, and approved dielectric grease.",
                    "Acid-resistant gloves, face shield, splash apron, and battery service checklist.",
                    "Portable fan for added airflow during extended inspection if the charging area is warm or enclosed.",
                ],
                [
                    "Wear acid-resistant PPE before opening the bay, even if no leak is visible.",
                    "Do not place metal tools on the battery top or bridge positive and negative terminals with a loose part or rag.",
                    "If swelling, cracked cases, or strong sulfur odor are present, stop work and escalate to the fleet supervisor immediately.",
                    "Use neutral cleaner only on approved surfaces and keep liquids away from control modules mounted above the battery tray.",
                ],
                [
                    "Park the truck in the designated service lane, key off, chock the wheels, and confirm no active charging cable is attached.",
                    "Open the battery bay and inspect hold-downs, tray rails, cable strain relief, and vent cap seating before touching residue.",
                    "Check for heat discoloration at the main connector and contactor leads. If discoloration is present, record the exact location and stop before reconnecting the truck for service.",
                    "Brush away dry residue first, then clean surfaces with neutral solution and absorbent pads. Do not flood the compartment.",
                    "Torque accessible hold-down hardware to the approved value on the checklist and replace missing cable ties or clips.",
                    "Verify that vent caps are seated evenly and that no cable is routed across a vent opening or sharp tray edge.",
                    "Apply a light film of dielectric grease only to approved connector surfaces, not to exposed cell tops or inspection labels.",
                    "Close the bay, power the truck, and confirm the unit starts without connector fault, battery disconnect warning, or lift inhibit message.",
                ],
                [
                    "No loose hardware, visible corrosion residue, or cable abrasion remains inside the battery bay.",
                    "Main connector housing shows no fresh heat marks or burnt odor after restart.",
                    "The truck powers up cleanly and completes a short drive, lift, and lower functional check.",
                    "The service checklist and any defect notes are attached to the fleet maintenance record before the truck returns to operation.",
                ],
                [
                    "Capture battery serial placeholder, truck ID, shift, and technician initials.",
                    "If corrosion was cleaned, note the severity as light, moderate, or heavy and whether follow-up inspection is required.",
                    "Open a corrective action ticket for any connector heat event, cracked vent cap, or damaged tray liner.",
                    "Log the restart result and the name of the supervisor who approved the truck for release.",
                ],
                [
                    "The most realistic training scenario for this guide is a truck that still starts normally but shows early connector discoloration near the charge lead. That creates a retrieval target for questions about when a forklift may continue in limited service and when it must be pulled immediately.",
                    "Another frequent scenario is repeated residue near one corner of the tray caused by poor cap seating after charging. The procedure should lead a reader to inspect vent cap fit before assuming a larger battery defect.",
                    "Because this is a public-safe sample, all identifiers are fictional and all maintenance outcomes are written as examples rather than statements about a real fleet.",
                ],
            ),
        )
    )
    docs.append(
        (
            "maintenance_procedures",
            "MP-03 HVAC Filter and Airflow Service Manual.pdf",
            *maintenance_doc(
                "MP-03 HVAC Filter and Airflow Service Manual",
                "MP-03-HVAC-RTU7",
                "This manual defines the quarterly service routine for the fictional RTU-7 rooftop HVAC unit serving office and staging areas. It covers filter replacement, condensate inspection, belt condition, airflow verification, and restart documentation.",
                [
                    "Roof access permit, multimeter, differential pressure gauge, spare filters, belt tension tool, flashlight, and hand brush.",
                    "Approved replacement filters with the exact MERV rating listed on the asset card.",
                    "Portable radio or phone for contact with the building coordinator during shutdown and restart.",
                    "Weather-appropriate fall protection and non-slip footwear for roof access.",
                ],
                [
                    "Do not access the roof during lightning, freezing precipitation, or sustained high wind conditions.",
                    "Use the local disconnect to isolate the unit before opening service panels.",
                    "Take care around hot surfaces near compressor lines and sharp cabinet edges inside filter and blower compartments.",
                    "If standing water is present near electrical sections, stop work and escalate before energizing the unit.",
                ],
                [
                    "Coordinate a service window with the building coordinator so occupants understand the temporary shutdown.",
                    "Isolate the RTU, verify fan stop, and inspect exterior panel condition, seals, and visible fasteners before opening the cabinet.",
                    "Remove used filters, compare size and rating to the asset card, and install matched replacements with airflow arrows oriented correctly.",
                    "Inspect blower belt wear, pulley alignment, condensate drain condition, and coil face cleanliness. Brush away loose debris without bending fins.",
                    "Measure differential pressure across the new filters after restart and compare it with the acceptable post-service band on the asset card.",
                    "Check supply and return temperature difference after the unit stabilizes for ten minutes.",
                    "Confirm all access panels are secured and that no tools or packaging remain inside the cabinet before final restart.",
                ],
                [
                    "Installed filters match size and MERV requirement with no bypass gaps.",
                    "Condensate path is clear and no standing water remains in the drain pan.",
                    "Belt tension is within the approved range and no abnormal vibration or squeal is present after restart.",
                    "Measured temperature split and filter differential pressure are within the unit baseline or have a documented reason for variance.",
                ],
                [
                    "Record filter size, quantity, and lot placeholder used during service.",
                    "Capture ambient outdoor temperature and supply-return delta at the time of final readings.",
                    "List any deferred roof or cabinet repairs separately from the routine filter task.",
                    "Attach photos only if the project later introduces media support; for Phase 1 and Phase 2 planning, note conditions in text.",
                ],
                [
                    "A realistic retrieval question for this manual would ask whether the temperature split is taken immediately after restart or after a stabilization period. The answer appears in the procedure steps and not in the acceptance criteria, which helps test precise grounding.",
                    "Another useful scenario involves the wrong filter rating arriving from stores. The manual implies the unit should not be closed out with a mismatched filter, even if airflow appears normal.",
                ],
            ),
        )
    )
    docs.append(
        (
            "policies",
            "POL-01 Document Retention and Redaction Policy.pdf",
            *policy_doc(
                "POL-01 Document Retention and Redaction Policy",
                "POL-01-GOV-110",
                "This policy defines how fictional project teams store, review, redact, publish, and retire documents that may be used in a public-facing AI demonstration environment. Its purpose is to prevent accidental inclusion of private, identifying, or proprietary material while preserving enough structure for realistic testing.",
                [
                    "Synthetic document: a file created entirely for demonstration or testing and not derived from private operational material.",
                    "Redacted document: a file whose sensitive content has been replaced with safe placeholders and reviewed for residual identifiers in text, metadata, and images.",
                    "Prohibited source: any real internal, customer, employee, vendor, or security-sensitive content that is not approved for unrestricted public release.",
                    "Derived artifact: OCR output, extracted text, embeddings, screenshots, logs, or caches produced from a prohibited source.",
                ],
                [
                    "Keep public repository sample data limited to synthetic or fully redacted content that a third party could inspect without restriction.",
                    "Store working drafts containing unresolved redactions only in a local excluded path until review is complete.",
                    "Review filenames, embedded metadata, document properties, and visible page content before any sample file is committed.",
                    "Retain synthetic demonstration documents as long as they support evaluation, examples, or user-interface testing, provided they remain current with the project scope.",
                    "Delete or replace sample documents that reference outdated controls, deprecated architectures, or naming patterns likely to confuse future reviewers.",
                ],
                [
                    "Do not commit real manuals, internal screenshots, vendor exports, customer notes, OCR output from private files, or debug logs derived from private materials.",
                    "Do not rely on simple name replacement if the surrounding details still reveal a real site, incident, employee, or customer context.",
                    "Do not copy policy language from a private handbook into a public sample even if obvious identifiers are removed.",
                    "Do not treat generated embeddings, vector indexes, or extracted chunks from private sources as safe simply because the original file is absent from the repository.",
                ],
                [
                    "If a team believes a real document excerpt is necessary for demonstration, it must be escalated to the policy owner and replaced with a synthetic reconstruction unless explicit written release approval exists.",
                    "If uncertainty remains after review, treat the material as prohibited until a second reviewer signs off on its safety.",
                    "Exception approvals must name the approving role, scope of use, expiration date, and required follow-up controls.",
                ],
                [
                    "Project maintainers should periodically sample the repository for unsafe artifacts, including PDF metadata, hidden spreadsheet tabs, OCR caches, and leftover local database files.",
                    "Violations require immediate removal from the branch, notification to the project owner, and a review of any downstream artifacts generated from the unsafe material.",
                    "Repeat violations should result in narrower contribution permissions until the contributor demonstrates understanding of the public-release boundary.",
                ],
            ),
        )
    )
    docs.append(
        (
            "policies",
            "POL-02 Field Device Access and Escalation Policy.pdf",
            *policy_doc(
                "POL-02 Field Device Access and Escalation Policy",
                "POL-02-OPS-205",
                "This policy defines how staff and contractors access fictional field devices, shared terminals, and handheld systems in a distributed operations environment. It balances uptime with traceability by requiring individual accountability, documented handoff, and a clear escalation path when normal access controls interfere with safe operations.",
                [
                    "Field device: any handheld scanner, forklift terminal, wall-mounted station, or service console used to perform operational work.",
                    "Shared terminal: a device used by more than one worker across a shift, where session handoff controls are required.",
                    "Emergency access event: a time-bounded use of elevated credentials to restore a blocked operation when normal access is unavailable.",
                    "Session owner: the person whose credentials are currently active on the device.",
                ],
                [
                    "Each person must use individual credentials when the device supports named sign-in. Shared generic logins may be used only where the device architecture cannot support named accounts and where a compensating log exists.",
                    "Devices left unattended must be locked, docked, or signed out according to the local timeout standard.",
                    "Handoffs between shifts must include device count, battery or charger state, visible damage notes, and confirmation that the prior session is closed.",
                    "Emergency access events must be approved by the shift lead and recorded with start time, end time, reason, and follow-up review owner.",
                    "Any field device that stores cached work after sign-out must be included in the end-of-shift audit checklist.",
                ],
                [
                    "Do not share named credentials verbally, by chat, or by leaving them written on the device, charger, or nearby workstation.",
                    "Do not bypass a lock screen by borrowing another worker's badge unless the event is recorded as an emergency access event.",
                    "Do not leave a session active on a forklift, packing station, or service cart during meal breaks or maintenance windows.",
                    "Do not continue using a device with suspected tampering, missing seals, or unexplained repeated login failures without escalation.",
                ],
                [
                    "If an operation cannot continue because a device is locked to a departed worker, notify the shift lead and service desk. The lead decides whether to wait for normal unlock, perform supervised emergency access, or move the work to a spare device.",
                    "If repeated session failures affect multiple devices in one area, escalate as a possible infrastructure or identity-provider incident rather than handling each device separately.",
                    "If a contractor requires temporary access beyond one shift, the sponsor manager must document the business reason and the expected end date before access is extended.",
                ],
                [
                    "Supervisors should audit at least one shared device handoff per week and verify that recorded handoffs match physical device location and condition.",
                    "The service desk should trend repeat emergency access events by site and by device family to identify training gaps or brittle login workflows.",
                    "Any unexplained mismatch between recorded session owner and observed user must be treated as a control failure until resolved.",
                ],
            ),
        )
    )
    docs.append(
        (
            "troubleshooting_guides",
            "TS-01 Label Printer Misalignment Troubleshooting Guide.pdf",
            *troubleshooting_doc(
                "TS-01 Label Printer Misalignment Troubleshooting Guide",
                "TS-01-PRN-410",
                "This guide helps frontline support and line leads diagnose label print drift, skew, and horizontal offset on the fictional PRN-410 thermal label printer used at packing lanes. It assumes the printer powers on and feeds media, but the printed image does not align consistently with the label stock.",
                [
                    "Printed barcodes drift toward the leading or trailing edge after several labels.",
                    "The first label after calibration looks correct, but the next ten labels walk out of position.",
                    "Left margin is acceptable on narrow labels but clipped on wide labels loaded from the same roll family.",
                    "Operators report frequent media-out or gap-sensor prompts after roll changes.",
                ],
                [
                    "Improper media sensor position after a roll change.",
                    "Print-head pressure imbalance or partially latched print-head assembly.",
                    "Incorrect label size, gap, or top-of-form setting in the workstation profile.",
                    "Contamination on the platen roller causing the stock to drift under tension.",
                ],
                [
                    "Confirm the exact label part number and compare it with the workstation profile currently assigned to the lane.",
                    "Inspect media path alignment marks and verify the movable guide lightly touches the stock without bowing it.",
                    "Clean the platen roller and sensor window, then print five blank feeds followed by a calibration page.",
                    "Print a ten-label test batch and note whether drift begins immediately or only after the printer warms up.",
                    "If the issue appears only on one workstation, compare page setup and printer preference values with a known-good lane using the same label size.",
                ],
                [
                    "Reseat the roll, reposition the media guide, and rerun calibration if the stock is visibly off center.",
                    "If software settings are wrong, correct label width, height, and top-of-form values, then print a fresh ten-label batch.",
                    "If drift persists after cleaning and settings validation, replace the platen roller and retest before escalating.",
                    "If a print-head latch is not closing evenly, remove the printer from service and swap in the spare lane device.",
                ],
                [
                    "Escalate after two failed recalibration attempts on the same stock.",
                    "Escalate immediately if the print head cannot latch evenly or if labels wrinkle under the print head.",
                    "Attach one successful sample label and one failed sample label to the service ticket if the issue is intermittent.",
                ],
                [
                    "A useful question for later RAG testing is whether the guide tells the operator to compare workstation settings with a known-good lane before replacing parts. It does, and that detail matters because many alignment issues are profile-related rather than hardware-related.",
                    "Another realistic variation is drift that appears only after warm-up. That hints at mechanical friction or roller condition instead of a simple gap-sensor position problem.",
                ],
            ),
        )
    )
    docs.append(
        (
            "troubleshooting_guides",
            "TS-02 Warehouse Scanner Sync Failure Guide.pdf",
            *troubleshooting_doc(
                "TS-02 Warehouse Scanner Sync Failure Guide",
                "TS-02-SCN-512",
                "This guide covers the fictional SCN-512 warehouse scanner when completed picks, moves, or counts do not sync promptly to the host system. It focuses on the difference between local device issues, wireless coverage problems, and backlog on the application side.",
                [
                    "Scanner shows completed work locally but the supervisor dashboard still displays the old queue state after several minutes.",
                    "Users see a sync-pending banner that clears and returns repeatedly without a hard error message.",
                    "Scanner reconnects to Wi-Fi after roaming but does not upload queued work until the app is restarted.",
                    "Multiple devices in one aisle report stale inventory positions after a wireless access point switchover.",
                ],
                [
                    "Weak or unstable wireless coverage causing repeated partial reconnects.",
                    "Clock drift or stale authentication token after the device resumes from a long dock period.",
                    "Application queue backlog on the local device caused by a stuck job record.",
                    "Server-side processing delay affecting multiple scanners at once.",
                ],
                [
                    "Check whether the problem is isolated to one scanner, one aisle, or an entire shift crew before making device-level changes.",
                    "Confirm Wi-Fi signal and roaming history on the device diagnostics page. Note whether reconnects occurred during the affected window.",
                    "Open the sync queue screen and look for one item that remains in retry longer than the others.",
                    "Verify device time, battery state, and token age if the unit has been docked for an extended period.",
                    "If multiple devices are affected, compare the observed time with any known network or application maintenance notice before clearing queues.",
                ],
                [
                    "If one stuck record blocks the queue, export the error summary, capture the job ID, and clear only the failed record according to the device support workflow.",
                    "If the token is stale, sign the user out, reconnect Wi-Fi, and sign back in before rerunning sync.",
                    "If roaming instability is evident, move to a known-good coverage area and confirm whether queued work uploads without restarting the app.",
                    "If the issue follows one device across areas, re-enroll the scanner profile and retest with a single sample transaction.",
                ],
                [
                    "Escalate to network support if multiple scanners in the same zone show reconnect churn or low signal history during the same time period.",
                    "Escalate to the application support team if multiple devices have healthy connectivity but their queues remain blocked by different records.",
                    "Escalate immediately if clearing the queue risks losing unposted inventory movements and no audit export is available.",
                ],
                [
                    "This guide intentionally distinguishes between a single stuck queue record and a broad outage because those produce different evidence. That makes it a stronger corpus document for later retrieval than a simple one-size-fits-all checklist.",
                    "A realistic user question might ask whether a scanner should be re-enrolled before or after checking whether the problem affects multiple devices. The guide says scope first, then re-enroll only if the issue follows one device.",
                ],
            ),
        )
    )
    docs.append(
        (
            "troubleshooting_guides",
            "TS-03 Dock Door Sensor Fault Isolation Guide.pdf",
            *troubleshooting_doc(
                "TS-03 Dock Door Sensor Fault Isolation Guide",
                "TS-03-DDR-330",
                "This guide supports first-response diagnosis of fictional dock door photo-eye faults, false obstruction alarms, and intermittent beam-loss events. It is intended for site support, maintenance leads, and supervisors deciding whether a door can remain in limited service.",
                [
                    "Door reverses immediately after closing even though the opening is clear.",
                    "Controller panel shows intermittent obstruction or beam-loss alarms that clear without manual reset.",
                    "Fault appears during sunrise or late-day glare on one door orientation only.",
                    "Door closes normally in manual hold-to-run mode but faults in automatic mode.",
                ],
                [
                    "Dirty or misaligned photo-eye lenses.",
                    "Cable strain or intermittent break near the moving side of the frame.",
                    "Sun glare or reflective shrink wrap causing false sensor readings.",
                    "Controller input instability or failing sensor power supply.",
                ],
                [
                    "Secure the lane and confirm no trailer movement, pedestrian activity, or forklift traffic will intersect the door while testing is in progress.",
                    "Inspect both lenses, brackets, and cable routing. Clean lenses before changing alignment.",
                    "Observe controller input lights while gently moving the cable near the travel point to identify intermittent breaks.",
                    "Test the door in manual mode and automatic mode to separate a control logic issue from a basic obstruction reading.",
                    "If glare is suspected, shade the receiver temporarily and note whether the fault clears under the same operating cycle.",
                ],
                [
                    "Realign brackets and retighten hardware if the beam path has shifted.",
                    "Replace damaged cable sections or sensor heads if intermittent input changes are confirmed.",
                    "Apply the approved glare shield or timing change only if the glare condition is documented and recurring on that door orientation.",
                    "If the controller input remains unstable after sensor replacement, place the door out of service and escalate to controls support.",
                ],
                [
                    "Escalate immediately if the door cannot be operated safely in either manual or automatic mode.",
                    "Escalate to controls support if input lights disagree with physical sensor state after lens cleaning and cable inspection.",
                    "Do not return the door to automatic service until three consecutive open-close cycles complete without false obstruction alarm.",
                ],
                [
                    "The distinction between glare and wiring faults creates a good retrieval target because both can look intermittent. The guide expects the reviewer to use controller input lights and temporary shading to separate them.",
                    "A later RAG evaluation could ask what evidence is needed before applying a glare shield. The answer should come from the diagnostic workflow and recovery sections together, not from a single sentence.",
                ],
            ),
        )
    )
    docs.append(
        (
            "troubleshooting_guides",
            "TS-04 Point of Sale Terminal Freeze Recovery Guide.pdf",
            *troubleshooting_doc(
                "TS-04 Point of Sale Terminal Freeze Recovery Guide",
                "TS-04-POS-115",
                "This guide addresses fictional checkout terminal freezes in a service counter environment where the screen becomes unresponsive, peripherals time out, or the sale application stops updating while the operating system remains partially alive.",
                [
                    "Touch input stops responding but the receipt printer still powers on normally.",
                    "Card reader or scanner disconnect prompts appear after the sale application stalls.",
                    "The terminal recovers after several minutes, but the in-progress transaction is left in an unknown state.",
                    "Freeze occurs repeatedly after logon at one counter but not on adjacent counters using the same network.",
                ],
                [
                    "Hung sale application process or exhausted local cache.",
                    "USB peripheral timeout causing the front-end app to wait indefinitely.",
                    "Corrupt user profile or counter-specific configuration.",
                    "Local hardware fault such as failing solid-state storage or overheating thin client.",
                ],
                [
                    "Ask whether payment was already authorized before restarting anything, and protect receipts or handwritten notes needed to reconcile the transaction later.",
                    "Check whether the freeze affects only the sale application or the entire shell by testing clock movement, cursor response, or a safe system hotkey.",
                    "Disconnect and reconnect one peripheral at a time only after documenting what was attached when the freeze occurred.",
                    "Compare the affected counter's config version, mapped printer, and scanner profile to a known-good adjacent counter.",
                    "Review local event logs or support panel indicators for repeated app crash, disk warning, or temperature messages.",
                ],
                [
                    "If the shell remains responsive, close and relaunch the sale application first and verify transaction recovery behavior.",
                    "If one peripheral repeatedly triggers the freeze after reconnect, replace it with a spare and retest before reimaging the terminal.",
                    "If the freeze follows one user profile across counters, clear the local profile cache and force a clean sign-in.",
                    "If storage or thermal warnings appear, remove the terminal from service and move checkout activity to a spare counter.",
                ],
                [
                    "Escalate immediately if payment state cannot be reconciled or if the terminal may have captured a card event without completing the sale record.",
                    "Escalate to desktop engineering if the freeze recurs on clean sign-in with no peripheral attached.",
                    "Escalate to application support if multiple counters show the same app stall after a new release or config change.",
                ],
                [
                    "This guide is more realistic because it forces the reader to protect transaction integrity before rebooting. That makes later no-answer testing more meaningful: a question about payment reconciliation should have a clear source-backed answer.",
                    "A good evaluation prompt would ask whether the operator should disconnect all peripherals at once. The guide says no; isolate peripherals one at a time after documenting the initial state.",
                ],
            ),
        )
    )
    docs.append(
        (
            "troubleshooting_guides",
            "TS-05 Packaging Line Jam Response Guide.pdf",
            *troubleshooting_doc(
                "TS-05 Packaging Line Jam Response Guide",
                "TS-05-PKG-605",
                "This guide helps operators and maintenance leads respond to fictional carton jams on the PKG-605 packaging line. It covers safe stop, jam classification, diverter checks, sensor disagreement, and restart validation after a cleared event.",
                [
                    "Cartons stop at the merge, diverter, or taper entry while upstream zones continue feeding.",
                    "A jam clears physically, but the HMI still shows a blocked zone or latched sensor state.",
                    "One jammed carton causes repeated short stops in the same zone across the shift.",
                    "Jam occurs only with taller cartons or mixed-SKU runs near the taper.",
                ],
                [
                    "Guide rail width set too narrow for the active carton family.",
                    "Diverter actuator slow to return or sticking under load.",
                    "Photo-eye blocked by label flap, tape tail, or reflective packaging.",
                    "Residual carton debris or a bowed carton causing repeat contact at one transfer point.",
                ],
                [
                    "Use the line stop for the affected zone, then confirm upstream release behavior so additional cartons are not pushed into the jam point.",
                    "Classify the event as simple obstruction, repeat obstruction in the same zone, or control-state mismatch where sensors disagree with physical conditions.",
                    "Inspect guide rails, diverter movement, belt transition points, and sensor faces before resetting the HMI fault.",
                    "If the fault persists after the obstruction is removed, compare sensor state on the HMI with the physical beam path and manual actuator position.",
                    "Check whether the affected carton family matches the setup recipe currently loaded on the line.",
                ],
                [
                    "Remove damaged cartons, clean debris, and adjust guide rails only to the approved recipe dimension.",
                    "Cycle the diverter manually if maintenance mode is allowed and verify full travel without drag or delayed return.",
                    "Reset the sensor only after confirming the beam path is clear and any label flap or tape tail has been removed.",
                    "Run five cartons of the affected SKU through the zone before returning the line to full rate.",
                ],
                [
                    "Escalate to maintenance if the same zone jams three times in one shift after guide and debris checks.",
                    "Escalate immediately if a diverter fails to return fully or if a manual cycle exposes abnormal resistance.",
                    "Do not resume mixed-SKU operation until a repeat jam on tall cartons has been tested with the correct recipe loaded.",
                ],
                [
                    "This guide creates useful retrieval opportunities because the correct action depends on whether the jam is a physical blockage or a control-state mismatch. Those are easy for a person to conflate and good for a RAG system to separate.",
                    "A later benchmark query could ask how many verification cartons to run before the line returns to full rate. The answer is specific and easy to cite if chunking preserves the restart section correctly.",
                ],
            ),
        )
    )
    return docs


def main() -> None:
    docs = build_documents()
    for folder, filename, metadata, sections in docs:
        target_dir = ROOT / folder
        target_dir.mkdir(parents=True, exist_ok=True)
        pages = paginate(filename[:-4], folder.replace("_", " ").title(), metadata, sections, minimum_pages=10)
        (target_dir / filename).write_bytes(build_pdf(pages))

    (ROOT / "README.md").write_text(
        "# Sample Data\n\n"
        "This folder contains synthetic, fictional PDF documents intended for portfolio-safe retrieval testing. The corpus is organized by document type so each category can be reviewed independently.\n\n"
        "## Maintenance Procedures\n"
        "- MP-01 Conveyor Belt Preventive Maintenance\n"
        "- MP-02 Forklift Battery Bay Service Procedure\n"
        "- MP-03 HVAC Filter and Airflow Service Manual\n\n"
        "## Policies\n"
        "- POL-01 Document Retention and Redaction Policy\n"
        "- POL-02 Field Device Access and Escalation Policy\n\n"
        "## Troubleshooting Guides\n"
        "- TS-01 Label Printer Misalignment Troubleshooting Guide\n"
        "- TS-02 Warehouse Scanner Sync Failure Guide\n"
        "- TS-03 Dock Door Sensor Fault Isolation Guide\n"
        "- TS-04 Point of Sale Terminal Freeze Recovery Guide\n"
        "- TS-05 Packaging Line Jam Response Guide\n\n"
        "All content is synthetic and safe for public release.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
