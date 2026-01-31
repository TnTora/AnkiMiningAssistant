#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <spa/param/video/format-utils.h>
#include <spa/debug/types.h>
#include <spa/param/video/type-info.h>

#include <pipewire/pipewire.h>

#include <string.h>
#include <stdlib.h>
 
/* [roundtrip] */
struct roundtrip_data {
        int pending;
        struct pw_main_loop *loop;
};

static void on_core_done(void *data, uint32_t id, int seq)
{
        struct roundtrip_data *d = data;
 
        if (id == PW_ID_CORE && seq == d->pending)
                pw_main_loop_quit(d->loop);
}

static void roundtrip(struct pw_core *core, struct pw_main_loop *loop)
{
        static const struct pw_core_events core_events = {
                PW_VERSION_CORE_EVENTS,
                .done = on_core_done,
        };
 
        struct roundtrip_data d = { .loop = loop };
        struct spa_hook core_listener;
        int err;
 
        pw_core_add_listener(core, &core_listener, &core_events, &d);
 
        d.pending = pw_core_sync(core, PW_ID_CORE, 0);
 
        if ((err = pw_main_loop_run(loop)) < 0)
                printf("main_loop_run error:%d!\n", err);
 
        spa_hook_remove(&core_listener);
}
/* [roundtrip] */

/* Get Object serial given node id */

struct obj_data {
        uint32_t node_id;
        int obj_id;
};

static void registry_event_global(void *data, uint32_t id,
                uint32_t permissions, const char *type, uint32_t version,
                const struct spa_dict *props)
{
        struct obj_data *obj_d = data;
        if (obj_d->node_id == id) {
                printf("object: id:%u type:%s/%d\n", id, type, version);

                const struct spa_dict_item *item;
                spa_dict_for_each(item, props) {
                        printf("\t\t%s: \"%s\"\n", item->key, item->value);
                        if (strcmp(item->key, "object.serial") == 0) {
                                char* p;
                                long ser = strtol(item->value, &p, 10);
                                obj_d->obj_id = (int) ser;
                        }
                }
                
        }
}

static const struct pw_registry_events registry_events = {
        PW_VERSION_REGISTRY_EVENTS,
        .global = registry_event_global,
};

static PyObject *method_get_serial(PyObject *self, PyObject *args)
{
        uint32_t node_id = -1;

        if (!PyArg_ParseTuple(args, "I", &node_id)) {
            return NULL;
        }
        
        printf("c_node: %d", node_id);

        if (node_id < 0) {
            // TODO: raise exception
            return NULL;
        }

        struct pw_main_loop *loop;
        struct pw_context *context;
        struct pw_core *core;
        struct pw_registry *registry;
        struct spa_hook registry_listener;
        
        struct obj_data obj_d = {.node_id = node_id, .obj_id = 0};
 
        pw_init(NULL, NULL);
 
        loop = pw_main_loop_new(NULL /* properties */);
        context = pw_context_new(pw_main_loop_get_loop(loop),
                        NULL /* properties */,
                        0 /* user_data size */);
 
        core = pw_context_connect(context,
                        NULL /* properties */,
                        0 /* user_data size */);
 
        registry = pw_core_get_registry(core, PW_VERSION_REGISTRY,
                        0 /* user_data size */);
 
        pw_registry_add_listener(registry, &registry_listener,
                                       &registry_events, &obj_d);
 
        roundtrip(core, loop);
 
        pw_proxy_destroy((struct pw_proxy*)registry);
        pw_core_disconnect(core);
        pw_context_destroy(context);
        pw_main_loop_destroy(loop);

        printf("object serial: %d\n", obj_d.obj_id);
 
        return PyLong_FromLong(obj_d.obj_id);
}

/* Get Object serial given node id */

struct data {
        struct pw_main_loop *loop;
        struct pw_stream *stream;
 
        struct spa_video_info format;
        struct spa_data curr_frame;
};

struct data shared_data = { 0, };

static PyObject *method_get_curr_frame(PyObject *self, PyObject *args) {
        if (!PyArg_ParseTuple(args, "", NULL)) {
                return NULL;
        }
        
        int w = shared_data.format.info.raw.size.width;
        int h = shared_data.format.info.raw.size.height;

        PyObject *bytes;
        if (shared_data.curr_frame.data == NULL){
          printf("No frame data\n");
          bytes = Py_None;
        } else {
          // printf("curr_frame size %d\n", shared_data.curr_frame.chunk->size);
          bytes = PyBytes_FromStringAndSize(shared_data.curr_frame.data, shared_data.curr_frame.chunk->size);
        }

        return Py_BuildValue("{s:i,s:i,s:O}", "width", w, "height", h, "data", bytes);
}

static PyObject *method_stop_stream(PyObject *self, PyObject *args) {
        if (!PyArg_ParseTuple(args, "", NULL)) {
                return NULL;
        }
        if (shared_data.loop == NULL) {
                return NULL;
        }
        pw_main_loop_quit(shared_data.loop);
        Py_RETURN_NONE;
        //return PyLong_FromLong(0);
}

static void on_process(void *userdata)
{
        struct data *data = userdata;
        struct pw_buffer *b;
        struct spa_buffer *buf;
 
        if ((b = pw_stream_dequeue_buffer(data->stream)) == NULL) {
                pw_log_warn("out of buffers: %m");
                return;
        }
 
        buf = b->buffer;
        if (buf->datas[0].data == NULL)
                return;

        data->curr_frame = buf->datas[0];
        // printf("got a frame of size %d\n", buf->datas[0].chunk->size);
        // printf("got bytes: %s\n", (char *) buf->datas[0].data);
 
        pw_stream_queue_buffer(data->stream, b);
}

static void on_param_changed(void *userdata, uint32_t id, const struct spa_pod *param)
{
        struct data *data = userdata;
 
        if (param == NULL || id != SPA_PARAM_Format)
                return;
 
        if (spa_format_parse(param,
                        &data->format.media_type,
                        &data->format.media_subtype) < 0)
                return;
 
        if (data->format.media_type != SPA_MEDIA_TYPE_video ||
            data->format.media_subtype != SPA_MEDIA_SUBTYPE_raw)
                return;
 
        if (spa_format_video_raw_parse(param, &data->format.info.raw) < 0)
                return;
 
        printf("got video format:\n");
        printf("  format: %d (%s)\n", data->format.info.raw.format,
                        spa_debug_type_find_name(spa_type_video_format,
                                data->format.info.raw.format));
        printf("  size: %dx%d\n", data->format.info.raw.size.width,
                        data->format.info.raw.size.height);
        printf("  framerate: %d/%d\n", data->format.info.raw.framerate.num,
                        data->format.info.raw.framerate.denom);
}

static const struct pw_stream_events stream_events = {
        PW_VERSION_STREAM_EVENTS,
        .param_changed = on_param_changed,
        .process = on_process,
};

static PyObject *method_start_stream(PyObject *self, PyObject *args)
{
        const char *node_serial;

        if (!PyArg_ParseTuple(args, "s", &node_serial)) {
                return NULL;
        }

        // if (node_serial < 0) {
        //         return NULL;
        // }

        // struct data data = { 0, };
        const struct spa_pod *params[1];
        uint8_t buffer[1024];
        struct spa_pod_builder b = SPA_POD_BUILDER_INIT(buffer, sizeof(buffer));
        struct pw_properties *props;
 
        pw_init(NULL, NULL);
 
        shared_data.loop = pw_main_loop_new(NULL);
 
        props = pw_properties_new(PW_KEY_MEDIA_TYPE, "Video",
                        PW_KEY_MEDIA_CATEGORY, "Capture",
                        PW_KEY_MEDIA_ROLE, "Screen",
                        PW_KEY_TARGET_OBJECT, node_serial,
                        NULL);
 
        shared_data.stream = pw_stream_new_simple(
                        pw_main_loop_get_loop(shared_data.loop),
                        "video-capture",
                        props,
                        &stream_events,
                        &shared_data);
 
        params[0] = spa_pod_builder_add_object(&b,
                SPA_TYPE_OBJECT_Format, SPA_PARAM_EnumFormat,
                SPA_FORMAT_mediaType,       SPA_POD_Id(SPA_MEDIA_TYPE_video),
                SPA_FORMAT_mediaSubtype,    SPA_POD_Id(SPA_MEDIA_SUBTYPE_raw),
                SPA_FORMAT_VIDEO_format,    SPA_POD_CHOICE_ENUM_Id(7,
                                                SPA_VIDEO_FORMAT_RGB,
                                                SPA_VIDEO_FORMAT_RGB,
                                                SPA_VIDEO_FORMAT_RGBA,
                                                SPA_VIDEO_FORMAT_RGBx,
                                                SPA_VIDEO_FORMAT_BGRx,
                                                SPA_VIDEO_FORMAT_YUY2,
                                                SPA_VIDEO_FORMAT_I420),
                SPA_FORMAT_VIDEO_size,      SPA_POD_CHOICE_RANGE_Rectangle(
                                                &SPA_RECTANGLE(320, 240),
                                                &SPA_RECTANGLE(1, 1),
                                                &SPA_RECTANGLE(4096, 4096)),
                SPA_FORMAT_VIDEO_framerate, SPA_POD_CHOICE_RANGE_Fraction(
                                                &SPA_FRACTION(25, 1),
                                                &SPA_FRACTION(0, 1),
                                                &SPA_FRACTION(1000, 1)));
 
        pw_stream_connect(shared_data.stream,
                          PW_DIRECTION_INPUT,
                          PW_ID_ANY,
                          PW_STREAM_FLAG_AUTOCONNECT |
                          PW_STREAM_FLAG_MAP_BUFFERS,
                          params, 1);
 
        Py_BEGIN_ALLOW_THREADS
        pw_main_loop_run(shared_data.loop);
        Py_END_ALLOW_THREADS
 
        pw_stream_destroy(shared_data.stream);
        pw_main_loop_destroy(shared_data.loop);
        
        shared_data.curr_frame.data = NULL;
 
        //return PyLong_FromLong(0);
        Py_RETURN_NONE;
}

// Python module definition

static PyMethodDef PipewireMethods[] = {
        {"get_obj_serial", method_get_serial, METH_VARARGS, "Get pipewire object serial given a node id"},
        {"get_curr_frame", method_get_curr_frame, METH_VARARGS, "Get current frame from stream"},
        {"stop_stream", method_stop_stream, METH_VARARGS, "Stop pipewire stream"},
        {"start_stream", method_start_stream, METH_VARARGS, "Start pipewire stream"},
        {NULL, NULL, 0, NULL}
};

static struct PyModuleDef pipewire_utilmodule = {
    PyModuleDef_HEAD_INIT,
    "pipewire_util",
    "interface with the pipewire library",
    -1,
    PipewireMethods
};

PyMODINIT_FUNC PyInit_pipewire_util(void) {
    return PyModule_Create(&pipewire_utilmodule);
}