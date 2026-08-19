"""Where the sending configuration comes from, and whose identity signs it.

🔴 THE CONNECTION IS SHARED, THE IDENTITY NEVER IS. One relay, one credential, one rotation
in a single place: that is what the shared store and Alice's console brought. But the address
and the name that say WHO is writing belong to a product. A scope writing from another's
domain sends a message the recipient is right to treat as a phishing attempt - and nothing
ever fails: the mail leaves, it arrives, and nobody sees another product's post.

⚠️ THESE GUARDS WATCH THE MOTIF, NOT A FIELD. The first version of the equivalent guard in
Alice watched only the sender NAME, because that was the field just repaired; the ADDRESS,
one line below in the same expression, kept its fallback the whole time. A guard narrower
than its rule reads exactly like a guard that holds it.
"""

from __future__ import annotations

import ast
import pathlib

import yaml

BACKEND = pathlib.Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent

#: Everything that says « who is writing ». Named as a set: adding an identity field without
#: listing it here is the gesture these guards exist to make visible.
IDENTITY_SETTINGS = ("SMTP_FROM_EMAIL", "SMTP_FROM_NAME")

#: The platform's other products. Written here because this repository does not carry the
#: registry - Alice does. One more brand gets noticed; one more field does not.
SIBLING_MARKS = (
    "lecomptoirimmo",
    "comptoirimmo",
    "Le Comptoir Immo",
    "Le Comptoir Alice",
    "Le Comptoir Séjour",
    "Le Comptoir Sejour",
    "Le Comptoir Market",
)


def test_no_sending_identity_defaults_to_another_products():
    """🔴 THE DEFAULT IS WHAT DOES THE DAMAGE, not the setting: whatever is written there
    becomes the signature of everybody who entered nothing."""
    from app.config import Settings

    faults = []
    for name in IDENTITY_SETTINGS:
        default = (Settings.model_fields[name].default or "").strip()
        if not default:
            continue  # empty: nobody inherits it, the only safe value
        for mark in SIBLING_MARKS:
            if mark.lower() in default.lower():
                faults.append(f"{name} = « {default} » carries « {mark} »")

    assert not faults, (
        "These shared defaults carry another product's identity:\n  "
        + "\n  ".join(faults)
        + "\n\nEmpty, the send refuses and says so, which is the right failure."
    )


def test_the_sending_address_has_no_default_at_all():
    """⚠️ A NAME CAN BE DERIVED FROM THE PRODUCT, AN ADDRESS CANNOT.

    « Le Comptoir Invest » is a safe default: it names this product. An address cannot be
    guessed - nobody knows which domain this fund owns - and a plausible default would be
    the worst case of all: it would send from an address that does not exist, in silence.
    """
    from app.config import Settings

    assert Settings.model_fields["SMTP_FROM_EMAIL"].default == "", (
        "The sending address carries a default. It is entered in Alice, « Système de "
        "communication », or the send refuses."
    )


def test_the_mailer_asks_alice_and_never_the_environment_directly():
    """🔴 THE PLATFORM'S RULE: the configuration comes from Alice, the environment is a
    fallback.

    Read from the source TREE: a mailer calling `get_settings()` would make this product the
    only one where a manager's change in the console does nothing - and nothing would fail,
    which is the costliest shape of defect in this repository.
    """
    source = (BACKEND / "app" / "services" / "mailer.py").read_text(encoding="utf-8")
    called = {
        getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
    }
    assert "get_settings" not in called, (
        "The mailer reads the environment directly. It must go through "
        "`comm_config.get_effective_comm()`, which lays Alice's values on top."
    )
    assert "get_effective_comm" in called, (
        "The mailer asks nobody for its configuration."
    )


def test_a_value_alice_leaves_empty_never_erases_the_local_one():
    """🔴 EMPTY OVERWRITES NOTHING, and it is the finest point of the merge.

    Alice no longer returns a shared address: a scope that entered none gets « ». If that
    empty string replaced the local value, filling the console in halfway would cut off
    sending for a product that worked - an outage caused by configuring.
    """
    from app.services.comm_config import _merge

    env = {"SMTP_HOST": "relay.local", "SMTP_FROM_EMAIL": "fund@example.test"}
    merged = _merge(env, {"smtp_host": "", "smtp_from_email": None})

    assert merged["SMTP_HOST"] == "relay.local"
    assert merged["SMTP_FROM_EMAIL"] == "fund@example.test"


def test_what_alice_does_say_wins_over_the_environment():
    """And the other half: what the console holds takes over, or centralising it would have
    served no purpose."""
    from app.services.comm_config import _merge

    merged = _merge(
        {"SMTP_HOST": "old.local", "SMTP_FROM_EMAIL": "old@example.test"},
        {"smtp_host": "relay.brevo", "smtp_from_email": "fund@example.test"},
    )

    assert merged["SMTP_HOST"] == "relay.brevo"
    assert merged["SMTP_FROM_EMAIL"] == "fund@example.test"


def test_the_backend_reads_the_shared_smtp_store_before_its_own_env():
    """🔴 THE SHARED STORE, AND THE ORDER THAT DECIDES WHO WINS.

    Before it, the relay's password lived in four copies and a rotation meant four hand
    edits. Invest was the FOURTH product and the only one absent from the store, because
    when it was created it sent nothing at all.

    ⚠️ THE ORDER IS HALF THE RULE: the shared file first, the product second. What follows
    wins, so Invest's identity stays Invest's, and a local override remains possible during
    an incident. Reversed, the store would overwrite the identity - the one thing that same
    store was built never to do.
    """
    faults = []
    for name in ("deploy", "prod"):
        path = ROOT / "docker" / f"docker-compose.{name}.yml"
        compose = yaml.safe_load(path.read_text(encoding="utf-8"))
        service = compose["services"]["invest-backend"]
        # An entry is either a plain string or a {path, required} mapping.
        files = [
            entry if isinstance(entry, str) else entry.get("path")
            for entry in service.get("env_file", [])
        ]
        shared = next(
            (i for i, f in enumerate(files) if "shared/smtp.env" in (f or "")), None
        )
        own = next((i for i, f in enumerate(files) if ".env.prod" in (f or "")), None)
        if shared is None:
            faults.append(f"{path.name}: the shared store is not mounted")
        elif own is None:
            faults.append(f"{path.name}: the product's own .env.prod is not mounted")
        elif shared > own:
            faults.append(f"{path.name}: the store is read AFTER the .env.prod")

    assert not faults, "\n  " + "\n  ".join(faults)
