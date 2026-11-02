
import re

# Words that don't help identify a fuel station's brand
STOP_WORDS = {
    "the", "truck", "stop", "stopping",
    "center", "centre", "travel", "station"
}


US_STATES = {
    "AL": "alabama",
    "NJ": "new jersey",
    "VA": "virginia",
    "TX": "texas",
    "AZ": "arizona",
    "WI": "wisconsin",
    "OK": "oklahoma",
    "AR": "arkansas",
    "IN": "indiana",
}

def normalize_name(name):
    if not name:
        return ""

    name = name.lower()

    # Remove punctuation and special characters
    name = re.sub(r"[^a-z0-9\s]", " ", name)

    # Remove extra spaces
    name = re.sub(r"\s+", " ", name).strip()

    return name


def name_matches(original_name, candidate_name):
    original = normalize_name(original_name)
    candidate = normalize_name(candidate_name)

    if not original or not candidate:
        return False

    original_words = set(original.split()) - STOP_WORDS
    candidate_words = set(candidate.split()) - STOP_WORDS

    if not original_words or not candidate_words:
        return False

    common_words = original_words.intersection(candidate_words)

    similarity = len(common_words) / len(original_words)

    return similarity >= 0.4


def normalize_state(state):
    if not state:
        return ""

    state = state.strip().lower()
    for abbreviation, full_name in US_STATES.items():
        if state == abbreviation.lower():
            return full_name

    return state


def location_matches(original_city, original_state, candidate_city, candidate_state):

    if not all([original_city, original_state, candidate_city, candidate_state]):
        return False

    original_city = original_city.strip().lower()
    candidate_city = candidate_city.strip().lower()

    original_state = normalize_state(original_state)
    candidate_state = normalize_state(candidate_state)

    return (
        original_city == candidate_city
        and original_state == candidate_state
    )



def extract_branch_number(name):
    if not name:
        return None

    match = re.search(r"#\s*(\d+)\b", name)
    return match.group(1) if match else None


def branch_number_conflicts(original_name, candidate_name):
    original_number = extract_branch_number(original_name)
    candidate_number = extract_branch_number(candidate_name)

    return (
        original_number is not None
        and candidate_number is not None
        and original_number != candidate_number
    )



def validate_candidate(original_name, original_city, original_state, candidate):
    properties = candidate.get("properties", {})

    candidate_name = properties.get("name", "")
    candidate_brand = properties.get("brand", "")

    alternate_names = properties.get("name_other", {})
    alternate_name = alternate_names.get("alt_name", "")

    candidate_names = [
        candidate_name,
        candidate_brand,
        alternate_name
    ]

    branch_conflict = any(
        branch_number_conflicts(original_name, name)
        for name in candidate_names
    )

    name_valid = (
        not branch_conflict
        and any(
            name_matches(original_name, name)
            for name in candidate_names
        )
    )

    candidate_city = properties.get("city", "")
    candidate_state = properties.get("state", "")

    location_valid = location_matches(
        original_city,
        original_state,
        candidate_city,
        candidate_state
    )

    return {
        "name_match": name_valid,
        "branch_number_conflict": branch_conflict,
        "location_match": location_valid,
        "candidate_name": candidate_name,
        "candidate_brand": candidate_brand,
        "alternate_name": alternate_name,
        "candidate_address": properties.get("formatted"),
        "latitude": properties.get("lat"),
        "longitude": properties.get("lon")
    }


def get_match_status(validation):
    if validation["name_match"] and validation["location_match"]:
        return "NEEDS_REVIEW"

    return "NOT_FOUND"


def find_best_candidate(original_name, original_city, original_state, candidates):

    best_candidate = None
    best_score = 0

    for candidate in candidates:

        validation = validate_candidate(
            original_name,
            original_city,
            original_state,
            candidate
        )
        if validation["branch_number_conflict"]:
          continue

        score = 0

        if validation["name_match"]:
            score += 2

        if validation["location_match"]:
            score += 1

        if score > best_score:
            best_score = score
            best_candidate = validation

    # Check only after examining all candidates
    if best_candidate is None or best_score < 3:
        return {
            "status": "NOT_FOUND",
            "score": best_score,
            "candidate": None
        }

    return {
        "status": get_match_status(best_candidate),
        "score": best_score,
        "candidate": best_candidate
    }