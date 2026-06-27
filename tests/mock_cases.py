"""Hand-crafted mock cases that exercise every branch of the pipeline.

Each entry is a raw row (as it would arrive from intake / the CSV) plus the
behaviour we expect, so tests can assert against it.
"""

MOCK_CASES = [
    {
        "label": "child at ghat during surge",
        "row": {"case_id": "M1", "age_band": "0-12", "mins_open": 35,
                "last_seen_location": "Ramkund Ghat", "high_risk_ctx": True,
                "reporter_mobile": None, "language": "Tamil", "status": "open",
                "physical_description": "boy ~6, crying"},
        "expect_floor": "ESCALATE", "expect_final_min": "CRITICAL",
    },
    {
        "label": "adult age_band but description is a child (mislabel)",
        "row": {"case_id": "M2", "age_band": "18-40", "mins_open": 50,
                "last_seen_location": "Panchavati Circle", "high_risk_ctx": False,
                "reporter_mobile": "+91 90000 00000", "language": "Hindi",
                "status": "open",
                "physical_description": "child in red shirt, about 8-10, crying"},
        "expect_floor": "OK", "expect_final_min": "ESCALATE",
        "expect_warning": "description suggests a child",
    },
    {
        "label": "elder long open at station",
        "row": {"case_id": "M3", "age_band": "80+", "mins_open": 100,
                "last_seen_location": "Nashik Road Station", "high_risk_ctx": False,
                "reporter_mobile": "+91 90000 00001", "language": "Telugu",
                "status": "open", "physical_description": "old man, white kurta"},
        "expect_floor": "CRITICAL", "expect_final_min": "CRITICAL",
    },
    {
        "label": "unknown age band -> default SLA",
        "row": {"case_id": "M4", "age_band": "25", "mins_open": 200,
                "last_seen_location": "Bus Stand Nashik", "high_risk_ctx": False,
                "reporter_mobile": "+91 90000 00002", "language": "Marathi",
                "status": "open", "physical_description": "man, blue shirt"},
        "expect_floor": "ESCALATE", "expect_final_min": "ESCALATE",
        "expect_warning": "unknown age_band",
    },
    {
        "label": "negative mins_open -> clamped",
        "row": {"case_id": "M5", "age_band": "41-60", "mins_open": -5,
                "last_seen_location": "Canada Corner", "high_risk_ctx": False,
                "reporter_mobile": "+91 90000 00003", "language": "Hindi",
                "status": "open", "physical_description": "woman, green saree"},
        "expect_floor": "OK", "expect_final_min": "OK",
        "expect_warning": "negative mins_open",
    },
    {
        "label": "teen at ghat (tightened SLA)",
        "row": {"case_id": "M6", "age_band": "13-17", "mins_open": 70,
                "last_seen_location": "Kushavart Kund", "high_risk_ctx": True,
                "reporter_mobile": None, "language": "Bengali", "status": "open",
                "physical_description": "teenage girl"},
        "expect_floor": "CRITICAL", "expect_final_min": "CRITICAL",
    },
]
