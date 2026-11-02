"""Explicit user edits preserve exercise identity, practice history, and source receipts."""


def edit_exercise(bank, exercise_id, *, question_text, answer, explanation, removed_asset_ids, reviewed):
    if not question_text.strip():
        raise ValueError('题干不能为空')
    record = bank.get(exercise_id)
    if record is None:
        raise LookupError('题目不存在')
    assets = record.extra_fields.get('source_attachments', [])
    removed = set(removed_asset_ids)
    if removed - {a['asset_id'] for a in assets}:
        raise ValueError('只能移除这道题已有的图片')
    record.question_text = question_text.strip()
    record.answer = answer.strip()
    record.explanation = explanation.strip()
    record.extra_fields['source_attachments'] = [a for a in assets if a['asset_id'] not in removed]
    if reviewed:
        record.extra_fields['import_review'] = dict(status='reviewed', issues=[])
    bank.update(record)
    return record
