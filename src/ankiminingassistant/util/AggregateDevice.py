# CoreAudio Taps references:
# https://developer.apple.com/documentation/coreaudio/capturing-system-audio-with-core-audio-taps?language=objc
# https://gist.github.com/directmusic/7d653806c24fe5bb8166d12a9f4422de
# Using objective c classes with objc framework: https://stackoverflow.com/a/1490644

import cffi

_ffi = cffi.FFI()
_ffi.cdef("""
// CoreFoundation/CFBase.h
typedef unsigned char           Boolean;
typedef unsigned int            UInt32;
typedef signed int              SInt32;
typedef SInt32                  OSStatus;
typedef unsigned long long      CFHashCode;
typedef signed long long        CFIndex;
typedef const void *            CFAllocatorRef;

// CoreFoundation/CFString.h
typedef const void *            CFStringRef;
typedef UInt32                  CFStringEncoding;
extern CFStringRef CFStringCreateWithCString(CFAllocatorRef alloc, const char *cStr, CFStringEncoding encoding);

// CoreFoundation/CFDictionary.h
typedef const void *            CFDictionaryRef;
typedef const void *            CFMutableDictionaryRef;
typedef const void *	        (*CFDictionaryRetainCallBack)(CFAllocatorRef allocator, const void *value);
typedef void		        (*CFDictionaryReleaseCallBack)(CFAllocatorRef allocator, const void *value);
typedef CFStringRef	        (*CFDictionaryCopyDescriptionCallBack)(const void *value);
typedef Boolean		        (*CFDictionaryEqualCallBack)(const void *value1, const void *value2);
typedef CFHashCode	        (*CFDictionaryHashCallBack)(const void *value);

typedef struct {
    CFIndex				version;
    CFDictionaryRetainCallBack		retain;
    CFDictionaryReleaseCallBack		release;
    CFDictionaryCopyDescriptionCallBack	copyDescription;
    CFDictionaryEqualCallBack		equal;
    CFDictionaryHashCallBack		hash;
} CFDictionaryKeyCallBacks;
typedef struct {
    CFIndex				version;
    CFDictionaryRetainCallBack		retain;
    CFDictionaryReleaseCallBack		release;
    CFDictionaryCopyDescriptionCallBack	copyDescription;
    CFDictionaryEqualCallBack		equal;
} CFDictionaryValueCallBacks;

extern CFMutableDictionaryRef CFDictionaryCreateMutable(
        CFAllocatorRef allocator,
        CFIndex capacity,
        const CFDictionaryKeyCallBacks *keyCallBacks,
        const CFDictionaryValueCallBacks *valueCallBacks);
extern void CFDictionaryAddValue(
        CFMutableDictionaryRef theDict,
        const void *key,
        const void *value);

// objc/objc.h
typedef struct objc_object *id;
typedef struct objc_selector *SEL;
extern SEL sel_registerName(const char *str);

// objc/message.h
extern id objc_msgSend(id self, SEL op, ...);

// objc/runtime.h
extern id objc_getClass(const char *name);

// CoreAudio/AudioHardwareBase.h
typedef UInt32 AudioObjectID;
typedef UInt32  AudioObjectPropertySelector;
typedef UInt32  AudioObjectPropertyScope;
typedef UInt32  AudioObjectPropertyElement;
struct  AudioObjectPropertyAddress
{
    AudioObjectPropertySelector mSelector;
    AudioObjectPropertyScope    mScope;
    AudioObjectPropertyElement  mElement;
};
typedef struct AudioObjectPropertyAddress AudioObjectPropertyAddress;

Boolean AudioObjectHasProperty(AudioObjectID inObjectID, const AudioObjectPropertyAddress* inAddress);

// CoreAudio/AudioHardwareTapping.h
extern OSStatus AudioHardwareCreateProcessTap(
        id inDescription,
        AudioObjectID *outTapID);
extern OSStatus AudioHardwareDestroyProcessTap(AudioObjectID inTapID);

// CoreAudio/AudioHardware.h
extern OSStatus AudioHardwareCreateAggregateDevice(
        CFDictionaryRef inDescription,
        AudioObjectID  *outDeviceID);
extern OSStatus AudioHardwareDestroyAggregateDevice(
        AudioObjectID inDeviceID);
""")


_ca = _ffi.dlopen("CoreAudio")
_cf = _ffi.dlopen("CoreFoundation")
_objc = _ffi.dlopen("objc")


def str_to_CFString(python_string):
    cstring = _ffi.new("char[]", bytes(python_string, "utf-8"))
    cfstring = _cf.CFStringCreateWithCString(_ffi.NULL, cstring, 0)
    return cfstring


# CoreAudio/AudioHardware.h
kAudioSubTapUIDKey = str_to_CFString("uid")
kAudioSubTapDriftCompensationKey = str_to_CFString("drift")
kAudioAggregateDeviceNameKey = str_to_CFString("name")
kAudioAggregateDeviceUIDKey = str_to_CFString("uid")
kAudioAggregateDeviceTapListKey = str_to_CFString("taps")
kAudioAggregateDeviceTapAutoStartKey = str_to_CFString("tapautostart")
kAudioAggregateDeviceIsPrivateKey = str_to_CFString("private")
kAudioAggregateDevicePropertyTapList = int.from_bytes(b"tap#", byteorder="big")

# CoreAudio/AudioHardwareBase.h
kAudioObjectPropertyScopeGlobal = int.from_bytes(b"glob", byteorder="big")
kAudioObjectPropertyElementMaster = 0


# Cast objc_msgSend to specify input. Needed on apple silicon.
msgSend = _ffi.cast("id(*)(id, SEL)", _objc.objc_msgSend)
msgSend_int = _ffi.cast("id(*)(id, SEL, int)", _objc.objc_msgSend)
msgSend_bool = _ffi.cast("id(*)(id, SEL, bool)", _objc.objc_msgSend)
msgSend_object = _ffi.cast("id(*)(id, SEL, id)", _objc.objc_msgSend)
msgSend_object_ptr = _ffi.cast("id(*)(id, SEL, id, void*)", _objc.objc_msgSend)
msgSend_CFString = _ffi.cast("id(*)(id, SEL, CFStringRef)", _objc.objc_msgSend)

sel_alloc = _objc.sel_registerName(b"alloc")
sel_init = _objc.sel_registerName(b"init")
sel_release = _objc.sel_registerName(b"release")
sel_autorelease = _objc.sel_registerName(b"autorelease")


def createAggregateDevice(name: str = "SystemAudioRecorder", *, private: bool = True) -> tuple:
    # Should avoid leaking memory when using objc
    NSAutoreleasePool = _objc.objc_getClass(b"NSAutoreleasePool")
    pool = msgSend(NSAutoreleasePool, sel_alloc)
    pool = msgSend(pool, sel_init)

    # Initializing variables equivalent to obj-c @YES ans @NO
    NSNumber = _objc.objc_getClass(b"NSNumber")
    YES = msgSend_int(NSNumber, _objc.sel_registerName(b"numberWithBool:"), _ffi.cast("bool", True))
    NO = msgSend_int(NSNumber, _objc.sel_registerName(b"numberWithBool:"), _ffi.cast("bool", False))

    # Initialize array that contains processes that should not be
    # captured. Leaving it empty will capture all system audio.
    NSArray = _objc.objc_getClass(b"NSArray")
    processes = msgSend(NSArray, _objc.sel_registerName(b"array"))

    CATapDescription = _objc.objc_getClass(b"CATapDescription")
    tap_desc = msgSend(CATapDescription, sel_alloc)
    tap_desc = msgSend_object(tap_desc, _objc.sel_registerName(b"initStereoGlobalTapButExcludeProcesses:"), processes)
    tap_desc = msgSend(tap_desc, sel_autorelease)
    msgSend_int(tap_desc, _objc.sel_registerName(b"setMuteBehavior:"), _ffi.cast("int", 0))
    msgSend_bool(tap_desc, _objc.sel_registerName(b"setPrivate:"), _ffi.cast("bool", private))
    msgSend_CFString(tap_desc, _objc.sel_registerName(b"setName:"), str_to_CFString("GlobalTap"))
    msgSend_bool(tap_desc, _objc.sel_registerName(b"setExclusive:"), _ffi.cast("bool", True))


    tap_id = _ffi.new("UInt32*")
    _ca.AudioHardwareCreateProcessTap(tap_desc, tap_id)

    tap_uid = msgSend(tap_desc, _objc.sel_registerName(b"UUID"))
    tap_uid_string = msgSend(tap_uid, _objc.sel_registerName(b"UUIDString"))

    tap_dict = _cf.CFDictionaryCreateMutable(_ffi.NULL, 0, _ffi.NULL, _ffi.NULL)
    _cf.CFDictionaryAddValue(tap_dict, kAudioSubTapUIDKey, tap_uid_string)
    _cf.CFDictionaryAddValue(tap_dict, kAudioSubTapDriftCompensationKey, YES)

    taps = msgSend(NSArray, sel_alloc)
    taps = msgSend_object_ptr(NSArray, _objc.sel_registerName(b"arrayWithObjects:"), tap_dict, _ffi.NULL)

    # Generate UUID for Aggregate device to avoid conflicts
    NSUUID = _objc.objc_getClass(b"NSUUID")
    uuid_str = msgSend(NSUUID, _objc.sel_registerName(b"UUID"))
    uuid_str = msgSend(uuid_str, _objc.sel_registerName(b"UUIDString"))

    aggregate_device_dict = _cf.CFDictionaryCreateMutable(_ffi.NULL, 0, _ffi.NULL, _ffi.NULL)
    _cf.CFDictionaryAddValue(aggregate_device_dict, kAudioAggregateDeviceNameKey, str_to_CFString(name))
    _ca.CFDictionaryAddValue(aggregate_device_dict, kAudioAggregateDeviceUIDKey, uuid_str)
    _cf.CFDictionaryAddValue(aggregate_device_dict, kAudioAggregateDeviceTapListKey, taps)
    _cf.CFDictionaryAddValue(aggregate_device_dict, kAudioAggregateDeviceTapAutoStartKey, NO)
    _cf.CFDictionaryAddValue(aggregate_device_dict, kAudioAggregateDeviceIsPrivateKey, YES if private else NO)

    aggr_id = _ffi.new("UInt32*")
    stat = _ca.AudioHardwareCreateAggregateDevice(aggregate_device_dict, aggr_id)

    msgSend(pool, _objc.sel_registerName(b"release"))

    if stat == 0:
        return aggr_id[0], tap_id[0]
    print(f"'AudioHardwareCreateAggregateDevice' Error Status: {stat}")
    _ca.AudioHardwareDestroyProcessTap(tap_id[0])
    return None, None


def isloopback(a_id: int) -> bool:
    prop = _ffi.new("AudioObjectPropertyAddress*", {
        "mSelector": kAudioAggregateDevicePropertyTapList,
        "mScope": kAudioObjectPropertyScopeGlobal,
        "mElement": kAudioObjectPropertyElementMaster})
    has_prop = _ca.AudioObjectHasProperty(a_id, prop)
    return bool(has_prop)


def destroyAggregateDevice(aggr_id: int, tap_id: int) -> None:
    _ca.AudioHardwareDestroyAggregateDevice(aggr_id)
    _ca.AudioHardwareDestroyProcessTap(tap_id)
