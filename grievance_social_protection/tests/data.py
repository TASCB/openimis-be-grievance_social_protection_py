VALID_TICKET_DESCRIPTION = " ".join([f"description{i}" for i in range(1, 46)])

# Ordinary priority: "High"/"Critical" tickets need the sensitive-closure right (127007) to close.


service_add_ticket_payload = {
    "category": "Default",
    "title": "Test",
    "description": VALID_TICKET_DESCRIPTION,
    "resolution": "8,7",
    "priority": "Normal",
    "date_of_incident": "2024-11-20",
    "channel": "Channel A",
    "flags": "Default",
}


service_add_ticket_payload_bad_resolution = {
    "category": "Default",
    "title": "Test",
    "description": VALID_TICKET_DESCRIPTION,
    "resolution": "sdasdasadsda",
    "priority": "Normal",
    "date_of_incident": "2024-11-20",
    "channel": "Channel A",
    "flags": "Default",
}


service_add_ticket_payload_bad_resolution_day = {
    "category": "Default",
    "title": "Test",
    "description": VALID_TICKET_DESCRIPTION,
    "resolution": "99,5",
    "priority": "Normal",
    "date_of_incident": "2024-11-20",
    "channel": "Channel A",
    "flags": "Default",
}


service_add_ticket_payload_bad_resolution_hour = {
    "category": "Default",
    "title": "Test",
    "description": VALID_TICKET_DESCRIPTION,
    "resolution": "1,54",
    "priority": "Normal",
    "date_of_incident": "2024-11-20",
    "channel": "Channel A",
    "flags": "Default",
}


service_update_ticket_payload = {
    "category": "Default",
    "title": "TestUpdate",
    "status": "OPEN",
    "resolution": "1,4",
    "priority": "Medium",
    "dateOfIncident": "2024-11-20",
    "channel": "Channel A",
    "flags": "Default",
}
