"""OCR damage signals select source review; they never delete source content."""
import re


def ocr_damage_reason(text):
    value = str(text or '').strip()
    if re.fullmatch(r'\[\s*(?:unreadable|illegible|unrecognized)\s*\]', value, re.I):
        return 'OCR未识别出文字'
    if len(value) >= 1500:
        repeated = re.search(r'(.{1,160}?)\1{12,}', value, re.S)
        if repeated and len(repeated[0]) >= max(1000, len(value) / 2):
            return 'OCR出现大段循环重复'
    return ''


def pending_ocr_damage(block):
    attributes = block.get('attributes', {}) if isinstance(block, dict) else block.attributes
    text = block.get('text', '') if isinstance(block, dict) else block.text
    if attributes.get('ocr_quality_confirmed'):
        return ''
    if attributes.get('ocr_quality_pending'):
        return attributes['ocr_quality_pending']
    return ocr_damage_reason(text)
