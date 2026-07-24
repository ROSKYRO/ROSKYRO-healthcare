# Central role registry — single source of truth for permissions across
# the customer app, partner app, and the internal ROSKYRO Team Dashboard.
# Direct port of server/src/utils/roles.js.

CUSTOMER_ROLES = ["owner", "staff", "doctor"]
PARTNER_ROLES = ["partner_admin", "partner_staff"]
ROSKYRO_ROLES = [
    "roskyro_admin",
    "roskyro_ops_manager",
    "roskyro_growth_expert",
    "roskyro_content_specialist",
    "roskyro_seo_specialist",
    "roskyro_gbp_specialist",
    "roskyro_review_manager",
    "roskyro_crm_executive",
    "roskyro_support_executive",
    "roskyro_quality_reviewer",
]

ALL_ROLES = CUSTOMER_ROLES + PARTNER_ROLES + ROSKYRO_ROLES


def app_shell_for(role: str) -> str:
    if role in CUSTOMER_ROLES:
        return "customer"
    if role in PARTNER_ROLES:
        return "partner"
    if role in ROSKYRO_ROLES:
        return "internal"
    return "unknown"


def is_internal(role: str) -> bool:
    return role in ROSKYRO_ROLES


def is_admin(role: str) -> bool:
    return role == "roskyro_admin"


def is_ops_or_admin(role: str) -> bool:
    return role in ("roskyro_admin", "roskyro_ops_manager")


def is_org_owner_or_staff(role: str) -> bool:
    return role in CUSTOMER_ROLES


def is_partner_user(role: str) -> bool:
    return role in PARTNER_ROLES
