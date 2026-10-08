from services.general_document_names import general_invoice_filename


def test_invoice_pdf_and_xml_share_a_recognizable_name():
    invoice = {
        "serie": "E",
        "folio": "347",
        "created_at": "2026-10-08T15:00:00Z",
        "cfdi_json": {
            "Fecha": "2026-05-31T12:30:00",
            "Receptor": {"Nombre": "GRUPO GASOLINERO AGRÍCOLA"},
        },
    }

    assert general_invoice_filename(invoice, "pdf") == (
        "GRUPO_GASOLINERO_AGRICOLA_MAYO_2026_E-347.pdf"
    )
    assert general_invoice_filename(invoice, "xml") == (
        "GRUPO_GASOLINERO_AGRICOLA_MAYO_2026_E-347.xml"
    )


def test_invoice_name_falls_back_to_receiver_rfc_and_uuid():
    invoice = {
        "uuid_sat": "00000000-1111-2222-3333-444444444444",
        "cfdi_json": {
            "Fecha": "2026-10-08T15:00:00",
            "Receptor": {"Rfc": "GGA000511GV0"},
        },
    }

    assert general_invoice_filename(invoice, "pdf") == (
        "GGA000511GV0_OCTUBRE_2026_00000000-1111-2222-3333-444444444444.pdf"
    )
