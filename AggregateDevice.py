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


_ca = _ffi.dlopen('CoreAudio')
_cf = _ffi.dlopen('CoreFoundation')
_objc = _ffi.dlopen('objc')

aggr_id = None
tap_id = None


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
kAudioAggregateDevicePropertyTapList = int.from_bytes(b'tap#', byteorder='big')

# CoreAudio/AudioHardwareBase.h
kAudioObjectPropertyScopeGlobal = int.from_bytes(b'glob', byteorder='big')
kAudioObjectPropertyElementMaster = 0


def createAggregateDevice():
    global tap_id, aggr_id
    # Not sure if this is necessary
    NSAutoreleasePool = _objc.objc_getClass(b'NSAutoreleasePool')
    pool = _objc.objc_msgSend(NSAutoreleasePool, _objc.sel_registerName(b'alloc'))
    pool = _objc.objc_msgSend(pool, _objc.sel_registerName(b'init'))

    # Initializing variables equivalent to obj-c @YES ans @NO
    NSNumber = _objc.objc_getClass(b'NSNumber')
    YES = _objc.objc_msgSend(NSNumber, _objc.sel_registerName(b'numberWithBool:'), _ffi.cast("bool", True))
    NO = _objc.objc_msgSend(NSNumber, _objc.sel_registerName(b'numberWithBool:'), _ffi.cast("bool", False))

    NSArray = _objc.objc_getClass(b'NSArray')
    processes = _objc.objc_msgSend(NSArray, _objc.sel_registerName(b'alloc'))
    processes = _objc.objc_msgSend(processes, _objc.sel_registerName(b'init'))

    CATapDescription = _objc.objc_getClass(b'CATapDescription')
    tap_desc = _objc.objc_msgSend(CATapDescription, _objc.sel_registerName(b'alloc'))
    tap_desc = _objc.objc_msgSend(tap_desc, _objc.sel_registerName(b'initStereoGlobalTapButExcludeProcesses:'), processes)
    _objc.objc_msgSend(tap_desc, _objc.sel_registerName(b'setMuteBehavior:'), _ffi.cast("int", 0))
    _objc.objc_msgSend(tap_desc, _objc.sel_registerName(b'setName:'), str_to_CFString("GlobalTap"))
    _objc.objc_msgSend(tap_desc, _objc.sel_registerName(b'setPrivate:'), _ffi.cast("bool", True))
    _objc.objc_msgSend(tap_desc, _objc.sel_registerName(b'setExclusive:'), _ffi.cast("bool", True))

    tap_id = _ffi.new("UInt32*")
    _ca.AudioHardwareCreateProcessTap(tap_desc, tap_id)

    tap_uid = _objc.objc_msgSend(tap_desc, _objc.sel_registerName(b'UUID'))
    tap_uid_string = _objc.objc_msgSend(tap_uid, _objc.sel_registerName(b'UUIDString'))

    tap_dict = _cf.CFDictionaryCreateMutable(_ffi.NULL, 0, _ffi.NULL, _ffi.NULL)
    _cf.CFDictionaryAddValue(tap_dict, kAudioSubTapUIDKey, tap_uid_string)
    _cf.CFDictionaryAddValue(tap_dict, kAudioSubTapDriftCompensationKey, YES)

    taps = _objc.objc_msgSend(NSArray, _objc.sel_registerName(b'alloc'))
    taps = _objc.objc_msgSend(taps, _objc.sel_registerName(b'initWithObjects:'), tap_dict, _ffi.NULL)

    aggregate_device_dict = _cf.CFDictionaryCreateMutable(_ffi.NULL, 0, _ffi.NULL, _ffi.NULL)
    _cf.CFDictionaryAddValue(aggregate_device_dict, kAudioAggregateDeviceNameKey, str_to_CFString("SystemAudioRecorder"))
    _cf.CFDictionaryAddValue(aggregate_device_dict, kAudioAggregateDeviceUIDKey, str_to_CFString("com.user.SystemAudioRecorder"))
    _cf.CFDictionaryAddValue(aggregate_device_dict, kAudioAggregateDeviceTapListKey, taps)
    _cf.CFDictionaryAddValue(aggregate_device_dict, kAudioAggregateDeviceTapAutoStartKey, NO)
    _cf.CFDictionaryAddValue(aggregate_device_dict, kAudioAggregateDeviceIsPrivateKey, YES)

    aggr_id = _ffi.new("UInt32*")
    stat = _ca.AudioHardwareCreateAggregateDevice(aggregate_device_dict, aggr_id)

    if stat == 0:
        return True
    else:
        return False


def isloopback(a_id):
    prop = _ffi.new("AudioObjectPropertyAddress*", {
        'mSelector': kAudioAggregateDevicePropertyTapList,
        'mScope': kAudioObjectPropertyScopeGlobal,
        'mElement': kAudioObjectPropertyElementMaster})
    has_prop = _ca.AudioObjectHasProperty(a_id, prop)
    return bool(has_prop)


def destroyAggregateDevice():
    _ca.AudioHardwareDestroyAggregateDevice(aggr_id[0])
    _ca.AudioHardwareDestroyProcessTap(tap_id[0])
