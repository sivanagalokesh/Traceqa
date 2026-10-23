from app.parser import parse_text

def test_duplicate_headings_remain_distinct():
    nodes=parse_text('1 Overview\nIntro text\n2 Operation\nFirst operation body\n3 Operation\nSecond operation body')
    operations=[n for n in nodes if n.heading.endswith('Operation')]
    assert len(operations)==2
    assert operations[0].logical_key != operations[1].logical_key
    assert operations[0].body_text != operations[1].body_text

def test_numbered_hierarchy_builds_parent_child():
    nodes=parse_text('1 Safety\nGeneral safety.\n1.1 Warnings\nWarning text.\n1.1.1 Electrical\nElectrical text.')
    by_heading={n.heading:n for n in nodes}
    assert by_heading['1.1 Warnings'].parent_index is not None
    assert nodes[by_heading['1.1 Warnings'].parent_index].heading=='1 Safety'
    assert nodes[by_heading['1.1.1 Electrical'].parent_index].heading=='1.1 Warnings'

def test_body_text_change_changes_hash():
    a=parse_text('1 Measurement\nMaximum pressure is 180 units.')
    b=parse_text('1 Measurement\nMaximum pressure is 190 units.')
    assert a[0].logical_key == b[0].logical_key
    assert a[0].content_hash != b[0].content_hash

def test_non_numbered_manual_is_not_dropped():
    nodes=parse_text('CARDIOTRACK MANUAL\nThis document describes the device and its operation.')
    assert nodes
    assert any('device' in n.body_text.lower() for n in nodes)


def test_missing_intermediate_heading_uses_nearest_existing_parent():
    nodes = parse_text(
        '2 Safety\nGeneral safety text.\n'
        '2.1 Intended Use\nIntended-use text.\n'
        '2.1.1.1 Battery Life Under Typical Use\nBattery text.'
    )
    by_heading = {n.heading: n for n in nodes}
    battery = by_heading['2.1.1.1 Battery Life Under Typical Use']
    assert battery.level == 4
    assert nodes[battery.parent_index].heading == '2.1 Intended Use'


def test_numbered_classification_list_with_colon_stays_in_body_text():
    nodes = parse_text(
        '4.1 Classification\n'
        '1. Normal: device operates as expected.\n'
        '2. Warning: device requires attention.'
    )
    assert len(nodes) == 1
    assert '1. Normal: device operates as expected.' in nodes[0].body_text
    assert '2. Warning: device requires attention.' in nodes[0].body_text


def test_page_sentinels_are_not_created_as_headings_and_body_is_preserved():
    nodes = parse_text(
        '1 Introduction\nFirst page paragraph.\n[PAGE 2]\n'
        'Continuation paragraph.'
    )
    assert len(nodes) == 1
    assert all('[PAGE' not in n.heading for n in nodes)
    assert 'First page paragraph.' in nodes[0].body_text
    assert 'Continuation paragraph.' in nodes[0].body_text
