"""Bottom/right Bayer crop metadata for aligned camera capture (no resampling).

Bottom-only crops of packed sensor rows can use the existing capture lease
without copying. Right crops need repacking under its packed-row lease
contract. This helper changes calibration only; it does not copy pixels.
Callers must supply matching cropped rows to file-based frontends.
"""
import copy
from fractions import Fraction
import struct

import raw_media as media


def _numbers(tag):
    if tag['type'] in (5,10):
        fmt='I' if tag['type']==5 else 'i'
        words=struct.unpack('<'+fmt*(tag['count']*2),media.unpack_record(tag))
        return tuple(Fraction(a,b) for a,b in zip(words[::2],words[1::2]))
    return tuple(Fraction(v) for v in media.values(tag))


def _rational(code,values):
    words=[]
    for value in values:
        value=Fraction(value);words.extend((value.numerator,value.denominator))
    return media.record(code,5,len(values),struct.pack('<'+'I'*len(words),*words))


def aligned(metadata,multiple=8):
    """Return top-left aligned geometry and an accounting record.

    Source origin and Bayer phase are unchanged. ActiveArea is intersected
    with retained pixels; DefaultCropSize is clipped at its original origin.
    Opaque XMP is omitted with an explicit receipt. Spatial opcode lists,
    masked areas, user crop and black-level delta arrays need dedicated
    transforms and are rejected when dimensions change.
    """
    media.validate(metadata)
    if type(multiple) is not int or multiple<2 or multiple>256 or multiple%2:
        raise ValueError('crop alignment must be even and in 2..256')
    result=copy.deepcopy(metadata)
    width=metadata['width']//multiple*multiple
    height=metadata['height']//multiple*multiple
    if width<48 or height<48:raise ValueError('aligned capture must retain at least 48x48 pixels')
    accounting=dict(source_width=metadata['width'],source_height=metadata['height'],
                    width=width,height=height,left=0,top=0,
                    removed_right_columns=metadata['width']-width,
                    removed_bottom_rows=metadata['height']-height,
                    omitted=[],changed_image_tags=[],changed_exif_tags=[])
    if (width,height)==(metadata['width'],metadata['height']):return result,accounting
    tags={t['code']:t for t in metadata['image']}
    for code in (50715,50716,50830,51125):
        if code in tags:raise ValueError(f'crop requires a dedicated spatial transform for tag {code}')
    for code in (51008,51009,51022):
        if code in tags and media.unpack_record(tags[code])!=bytes(4):
            raise ValueError(f'crop does not transform nonempty opcode list {code}')
    top,left,bottom,right=_numbers(tags[50829]) if 50829 in tags else (0,0,metadata['height'],metadata['width'])
    if any(Fraction(v).denominator!=1 for v in (top,left,bottom,right)):
        raise ValueError('crop requires integral active-area coordinates')
    bottom=min(bottom,height);right=min(right,width)
    if bottom<=top or right<=left:raise ValueError('crop removes the active image')
    origin=_numbers(tags[50719]) if 50719 in tags else (0,0)
    old_size=_numbers(tags[50720]) if 50720 in tags else (
        metadata['width']-left,metadata['height']-top)
    size=(min(old_size[0],right-left-origin[0]),min(old_size[1],bottom-top-origin[1]))
    if min(size)<=0:raise ValueError('crop removes the default image')
    replacements={50829:media.record(50829,4,4,struct.pack('<4I',*(int(v) for v in (top,left,bottom,right)))),
                  50719:_rational(50719,origin),50720:_rational(50720,size)}
    image=[]
    for tag in result['image']:
        code=tag['code']
        if code==700:
            accounting['omitted'].append(dict(code=700,reason='opaque XMP may contain stale crop geometry'));continue
        if code not in replacements:image.append(tag)
    for code,tag in replacements.items():
        if code not in tags or tag!=tags[code]:accounting['changed_image_tags'].append(code)
        image.append(tag)
    result['image']=image;result['width']=width;result['height']=height
    for i,tag in enumerate(result['exif']):
        if tag['code'] in (40962,40963):
            value=width if tag['code']==40962 else height
            result['exif'][i]=media.record(tag['code'],4,1,struct.pack('<I',value))
            accounting['changed_exif_tags'].append(tag['code'])
    media.validate(result)
    return result,accounting
