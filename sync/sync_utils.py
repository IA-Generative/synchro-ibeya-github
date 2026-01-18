import re


def extract_id_and_clean_for_kind(text, kind=None):
    """Auto-detect a bracketed tag/ID and return (cleaned_text, detected_kind, pi_number, item_number).

    detected_kind ∈ {'Features', 'Risques', 'Dependances', 'tobj', 'utobj', 'Issues', None}
    
    Attention :
        la nature du contenue correspond également au nom de la table dans Grist
        sauf pour utobj et tobj qui sont gardés tels quels > table 'Objectives' avec une colonne 'commited'
    
    Rules (case-insensitive):
      - feature tag: [Feat] ; feature id: [FP<pi>-<item>]
      - risk tag:    [Rsk] ou [Risk]
      - risk id:     [RP<pi>-<item>]
      - risk id+:    [RP<pi>-E-<epic>-<item>], [RiskP<pi>-E-<epic>-<item>] (E-001 ou E001 acceptés)
      
      - dep tag:     [DP]
      - dep id:      [DP<pi>-<item>]
      - dep id+:     [DP<pi>-E-<epic>-R<item>], [DP<pi>-E<epic>-R<item>] (E-001 ou E001 acceptés)
      - tobj tag:    [TObj] ; tobj id:    [TObjP<pi>-<item>]
      - utobj tag:   [uTObj]; utobj id:   [uTObjP<pi>-<item>]
      - issue tag:   [Bug], [Issue]; issue id: [IssueP<pi>-<item>]

    Behavior:
      - Finds the first bracketed token that matches ANY known tag/id.
      - Removes ONLY that bracket occurrence from the text.
      - Parses pi/item numbers only for id patterns; for tags-only keeps both numbers = 0.
      - If no known pattern is found, returns (cleaned_text, None, 0, 0).
      - If `text` is not a string, returns (text, None, 0, 0).
      - Always strips leading non-alphanumeric characters from the cleaned text.
    """
    if not isinstance(text, str):
        return text, None, 0, 0

    bracket_re = re.compile(r"\[([^\[\]]+)\]")

    # Precompiled per-kind token matchers (case-insensitive)
    id_fp_re = re.compile(r"^FP(\d+)-(\d+)$", re.IGNORECASE)
    id_fp_short_re = re.compile(r"^FP-(\d+)$", re.IGNORECASE)
    id_rp_re = re.compile(r"^RP(\d+)-(\d+)$", re.IGNORECASE)
    id_rp_epic_re = re.compile(r"^(?:RP|RiskP)(\d+)?-E-?(\d+)-(\d+)$", re.IGNORECASE)
    id_dp_re = re.compile(r"^DP(\d+)-(\d+)$", re.IGNORECASE)
    id_dp_epic_re = re.compile(r"^DP(\d+)?-E-?(\d+)-R?(\d+)$", re.IGNORECASE)
    id_tobj_re = re.compile(r"^TObjP(\d+)-(\d+)$", re.IGNORECASE)
    id_utobj_re = re.compile(r"^uTObjP(\d+)-(\d+)$", re.IGNORECASE)
    id_issue_re = re.compile(r"^IssueP(\d+)-(\d+)$", re.IGNORECASE)

    tag_feat_re = re.compile(r"^feat$", re.IGNORECASE)
    tag_rsk_re = re.compile(r"^rsk$", re.IGNORECASE)
    tag_risk_re = re.compile(r"^risk$", re.IGNORECASE)

    tag_dp_re = re.compile(r"^dp$", re.IGNORECASE)
    tag_dep_re = re.compile(r"^dep$", re.IGNORECASE)
    tag_tobj_re = re.compile(r"^tobj$", re.IGNORECASE)
    tag_utobj_re = re.compile(r"^utobj$", re.IGNORECASE)
    tag_bug_re = re.compile(r"^bug$", re.IGNORECASE)
    tag_issue_re = re.compile(r"^issue$", re.IGNORECASE)

    detected_kind = None
    pi_number = 0
    item_number = 0
    token_to_remove = None

    # Find first bracketed token that matches any known tag/id
    for m in bracket_re.finditer(text):
        token = m.group(1).strip()

        m_fp = id_fp_re.match(token)
        if m_fp:
            detected_kind = "Features"
            pi_number = int(m_fp.group(1))
            item_number = int(m_fp.group(2))
            token_to_remove = m.group(0)
            break

        m_fp_short = id_fp_short_re.match(token)
        if m_fp_short:
            detected_kind = "Features"
            pi_number = 0
            item_number = int(m_fp_short.group(1))
            token_to_remove = m.group(0)
            break

        m_rp = id_rp_re.match(token)
        if m_rp:
            detected_kind = "Risques"
            pi_number = int(m_rp.group(1))
            item_number = int(m_rp.group(2))
            token_to_remove = m.group(0)
            break

        m_rp_epic = id_rp_epic_re.match(token)
        if m_rp_epic:
            detected_kind = "Risques"
            # group(1) is optional PI number (e.g., RiskP3-...), group(2) is epic (E-001/E001), group(3) is item
            pi_number = int(m_rp_epic.group(1)) if m_rp_epic.group(1) else 0
            item_number = int(m_rp_epic.group(3))
            token_to_remove = m.group(0)
            break

        m_dp = id_dp_re.match(token)
        if m_dp:
            detected_kind = "Dependances"
            pi_number = int(m_dp.group(1))
            item_number = int(m_dp.group(2))
            token_to_remove = m.group(0)
            break

        m_dp_epic = id_dp_epic_re.match(token)
        if m_dp_epic:
            detected_kind = "Dependances"
            # group(1) is optional PI number, group(2) is epic (E-001/E001), group(3) is item (R001 or 001)
            pi_number = int(m_dp_epic.group(1)) if m_dp_epic.group(1) else 0
            item_number = int(m_dp_epic.group(3))
            token_to_remove = m.group(0)
            break

        m_tobj = id_tobj_re.match(token)
        if m_tobj:
            detected_kind = "tobj"
            pi_number = int(m_tobj.group(1))
            item_number = int(m_tobj.group(2))
            token_to_remove = m.group(0)
            break

        m_utobj = id_utobj_re.match(token)
        if m_utobj:
            detected_kind = "utobj"
            pi_number = int(m_utobj.group(1))
            item_number = int(m_utobj.group(2))
            token_to_remove = m.group(0)
            break

        m_issue = id_issue_re.match(token)
        if m_issue:
            detected_kind = "Issues"
            pi_number = int(m_issue.group(1))
            item_number = int(m_issue.group(2))
            token_to_remove = m.group(0)
            break

        if tag_feat_re.match(token):
            detected_kind = "Features"
            token_to_remove = m.group(0)
            break

        if tag_rsk_re.match(token) or tag_risk_re.match(token): 
            detected_kind = "Risques"
            token_to_remove = m.group(0)
            break

        if tag_dp_re.match(token) or tag_dep_re.match(token):
            detected_kind = "Dependances"
            token_to_remove = m.group(0)
            break

        if tag_tobj_re.match(token):
            detected_kind = "tobj"
            token_to_remove = m.group(0)
            break

        if tag_utobj_re.match(token):
            detected_kind = "utobj"
            token_to_remove = m.group(0)
            break

        if tag_bug_re.match(token) or tag_issue_re.match(token):
            detected_kind = "Issues"
            token_to_remove = m.group(0)
            break

    # Remove only the matched bracket occurrence (if any)
    if token_to_remove:
        cleaned_text = re.sub(re.escape(token_to_remove), "", text, count=1)
    else:
        cleaned_text = text

    cleaned_text = re.sub(r"^[^a-zA-Z0-9]+", "", cleaned_text).strip()
    return cleaned_text, detected_kind, pi_number, item_number


def extract_feature_id_and_clean(text):
    """Extract feature only: [Feat] or [FP<pi>-<item>]. Returns (cleaned_text, pi_number, item_number) or (cleaned_text, None, None) if not a feature."""
    cleaned_text, detected_kind, pi_number, item_number = extract_id_and_clean_for_kind(text)
    if detected_kind == "Features":
        return cleaned_text, pi_number, item_number
    return cleaned_text, None, None


def extract_issue_id_and_clean(text):
    """Extract issue only: [Bug], [Issue] or [IssueP<pi>-<item>].

    Returns (cleaned_text, pi_number, item_number) if an issue is detected,
    otherwise (cleaned_text, None, None).
    """
    cleaned_text, detected_kind, pi_number, item_number = extract_id_and_clean_for_kind(text)
    if detected_kind == "Issues":
        return cleaned_text, pi_number, item_number
    return cleaned_text, None, None


def extract_risk_id_and_clean(text):
    """Extract risk only: [Rsk] or [RP<pi>-<item>]. Returns (cleaned_text, pi_number, item_number) or (cleaned_text, None, None) if not a risk."""
    cleaned_text, detected_kind, pi_number, item_number = extract_id_and_clean_for_kind(text)
    if detected_kind == "Risques":
        return cleaned_text, pi_number, item_number
    return cleaned_text, None, None


def extract_dependence_id_and_clean(text):
    """Extract dependency only: [DP] or [DP<pi>-<item>]. Returns (cleaned_text, pi_number, item_number) or (cleaned_text, None, None) if not a dependency."""
    cleaned_text, detected_kind, pi_number, item_number = extract_id_and_clean_for_kind(text)
    if detected_kind == "Dependances":
        return cleaned_text, pi_number, item_number
    return cleaned_text, None, None


def extract_objective_id_and_clean(text):
    """Extract a team objective only.

    Accepted patterns (case-insensitive):
      - Committed team objective:   [TObj] or [TObjP<pi>-<item>]
      - Uncommitted team objective: [uTObj] or [uTObjP<pi>-<item>]

    Returns:
      - If objective detected: (cleaned_text, pi_number, item_number, commitment)
        where commitment is "committed" or "uncommitted".
      - If not an objective: (cleaned_text, None, None, None)

    Note: For tag-only patterns ([TObj] / [uTObj]) pi_number and item_number are 0.
    """
    cleaned_text, detected_kind, pi_number, item_number = extract_id_and_clean_for_kind(text)

    if detected_kind == "tobj":
        return cleaned_text, pi_number, item_number, "committed"

    if detected_kind == "utobj":
        return cleaned_text, pi_number, item_number, "uncommitted"

    return cleaned_text, None, None, None
