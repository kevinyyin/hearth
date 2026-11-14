"""Checks a model-written acknowledgment before it is spoken. Fails closed: a dropped acknowledgment costs nothing."""
import re

MAX_WORDS = 12
# shortcut: a word list, not a model; it blocks anything near help, arrival, timing, safety, numbers or advice.
# Upgrade to a classifier only if real acknowledgments are being dropped too often.
_BLOCK = re.compile(r"""\d|\b(
    help|coming|come|comes|way|headed|heading|route|arriv\w*|deliver\w*|driver|drive|ride|pick\w*|send\w*|sent|
    dispatch\w*|ambulance|tank|crew|truck|van|car|someone|somebody|they|they're|will|won't|\w+'ll|going|gonna|
    soon|shortly|minute\w*|hour\w*|today|tonight|tomorrow|morning|afternoon|evening|asap|right\s+away|immediately|
    almost|nearly|nearby|outside|there|here|safe\w*|fine|worry|guarantee\w*|promise\w*|sure|everything|
    oxygen|liter\w*|litre\w*|dose|setting\w*|turn|medic\w*|doctor|nurse|breath\w*|battery|power|backup|supply|supplies|
    one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty|half|quarter
)\b""", re.IGNORECASE | re.VERBOSE)


def allows(model_text: str) -> bool:
    """False if the text could imply help is coming, safety, timing, a number, or medical advice."""
    return len(model_text.split()) <= MAX_WORDS and not _BLOCK.search(model_text)
