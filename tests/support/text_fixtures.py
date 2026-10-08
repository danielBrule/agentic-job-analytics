"""Synthetic long descriptions with stable paragraphs and one changed section."""


_SECTIONS = [
    "Role overview\n" + "Build applied AI tools for synthetic enterprise customers. " * 30,
    "Discovery\n" + "Work with users to define requirements and evaluate prototypes. " * 30,
    "Production\n" + "Own deployment, monitoring and reliable operation of delivered systems. " * 30,
    "Team\n" + "Collaborate with engineers and product colleagues with limited line management. " * 30,
]
_ORIGINAL = "\n\n".join(_SECTIONS)
TEXT_FIXTURES = {
    "long_job_description": _ORIGINAL,
    "long_job_description_v1": _ORIGINAL,
    "long_job_description_v2_one_section_changed": "\n\n".join(
        _SECTIONS[:2] + ["Production\n" + "Own cloud deployment and incident response for customer systems. " * 30] + _SECTIONS[3:]
    ),
}
