/* Ren'Py adapter for the unmodified official Spine 4.3 C++ runtime.
 * ABI 2 uses portable operation journals in native.py for exact restoration.
 * See vendor-4.3/LICENSE. No private runtime fields are accessed.
 */
#include <spine/spine.h>
#include <spine/SkeletonRenderer.h>
#include <spine/Extension.h>
#include <vector>
#include <cstring>
#include <cstdio>
#include <cstdint>
#include <algorithm>
#include <exception>

using namespace spine;
namespace spine { SpineExtension *getDefaultExtension() { return new DefaultSpineExtension(); } }
#ifdef _WIN32
#define API extern "C" __declspec(dllexport)
#else
#define API extern "C" __attribute__((visibility("default")))
#endif

struct RspBatch {
    int page, blend, vertices, indices;
    float *xy, *attributes;
    uint32_t *triangles;
    int vertexCapacity, indexCapacity;
};
struct RspEvent {
    int type, track, integer;
    float time, number, volume, balance;
    char name[192], text[512], audio[384];
};
struct RspOverride { int bone, mask; float value[7]; };
class TextureHandles : public TextureLoader {
    int count = 0;
public:
    void load(AtlasPage &page, const String &) override { page.texture = (void *)(intptr_t)(++count); }
    void unload(void *) override {}
};
struct Buffers {
    std::vector<float> xy, attributes;
    std::vector<uint32_t> triangles;
    RspBatch batch;
};
struct Rsp {
    TextureHandles textures;
    Atlas *atlas = nullptr;
    SkeletonData *data = nullptr;
    Skeleton *skeleton = nullptr;
    AnimationStateData *mix = nullptr;
    AnimationState *state = nullptr;
    SkeletonRenderer renderer;
    std::vector<Buffers> buffers;
    std::vector<RspOverride> overrides;
    std::vector<RspEvent> events;
    float bounds[4] = {};
    int batchCount = 0;
    ~Rsp() { delete state; delete mix; delete skeleton; delete data; delete atlas; }
};
static void copy_text(char *out, const char *text, size_t size) { snprintf(out, size, "%s", text ? text : ""); }
static void listener(AnimationState *, EventType type, TrackEntry *entry, Event *event, void *user) {
    Rsp *r = (Rsp *)user;
    if ((type != EventType_Event && type != EventType_Complete) || r->events.size() >= 256) return;
    RspEvent out = {};
    out.type = type == EventType_Complete ? 3 : 5;
    out.track = entry->getTrackIndex();
    if (event) {
        out.time=event->getTime(); out.integer=event->getInt(); out.number=event->getFloat();
        out.volume=event->getVolume(); out.balance=event->getBalance();
        copy_text(out.name,event->getData().getName().buffer(),sizeof(out.name));
        copy_text(out.text,event->getString().buffer(),sizeof(out.text));
        copy_text(out.audio,event->getData().getAudioPath().buffer(),sizeof(out.audio));
    } else copy_text(out.name,entry->getAnimation().getName().buffer(),sizeof(out.name));
    r->events.push_back(out);
}
API int rsp_abi() { return 2; }
API const char *rsp_runtime_version() { return "4.3"; }
API void rsp_dispose(Rsp *r) { delete r; }
API Rsp *rsp_create(const char *atlas, int atlasLength, const unsigned char *data, int length,
                    int json, float scale, char *error, int errorLength) {
    Rsp *r = nullptr;
    try {
        r = new Rsp();
        Bone::setYDown(false);
        r->atlas = new Atlas(atlas,atlasLength,"",&r->textures);
        if (r->atlas->getPages().size() == 0) { copy_text(error,"Invalid Spine atlas",errorLength); delete r; return nullptr; }
        for (size_t i=0; i<r->atlas->getPages().size(); i++) {
            AtlasPage *page=r->atlas->getPages()[i];
            if (page->width<=0 || page->height<=0) { copy_text(error,"Atlas requires explicit page size",errorLength); delete r; return nullptr; }
        }
        if (json) {
            SkeletonJson reader(*r->atlas); reader.setScale(scale);
            r->data=reader.readSkeletonData((const char *)data);
            if (!r->data) copy_text(error,reader.getError().buffer(),errorLength);
        } else {
            SkeletonBinary reader(*r->atlas); reader.setScale(scale);
            r->data=reader.readSkeletonData(data,length);
            if (!r->data) copy_text(error,reader.getError().buffer(),errorLength);
        }
        if (!r->data) { delete r; return nullptr; }
        r->skeleton=new Skeleton(*r->data);
        r->mix=new AnimationStateData(*r->data); r->mix->setDefaultMix(0.2f);
        r->state=new AnimationState(*r->mix); r->state->setListener(listener,r);
        r->skeleton->updateWorldTransform(Physics_Update);
        return r;
    } catch (const std::exception &e) { copy_text(error,e.what(),errorLength); delete r; return nullptr; }
}
API int rsp_animation_count(Rsp *r) { return (int)r->data->getAnimations().size(); }
API const char *rsp_animation_name(Rsp *r,int i) { return r->data->getAnimations()[i]->getName().buffer(); }
API float rsp_animation_duration(Rsp *r,int i) { return r->data->getAnimations()[i]->getDuration(); }
API int rsp_bone_count(Rsp *r) { return (int)r->data->getBones().size(); }
API const char *rsp_bone_name(Rsp *r,int i) { return r->data->getBones()[i]->getName().buffer(); }
API int rsp_page_count(Rsp *r) { return (int)r->atlas->getPages().size(); }
API const char *rsp_page_name(Rsp *r,int i) { return r->atlas->getPages()[i]->name.buffer(); }
API int rsp_skin(Rsp *r,const char *name) {
    Skin *skin=r->data->findSkin(name); if (!skin) return 0;
    r->skeleton->setSkin(skin); return 1;
}
API void rsp_default_mix(Rsp *r,float duration) { r->mix->setDefaultMix(duration); }
API int rsp_mix(Rsp *r,const char *a,const char *b,float duration) {
    if (!r->data->findAnimation(a) || !r->data->findAnimation(b)) return 0;
    r->mix->setMix(a,b,duration); return 1;
}
API int rsp_play(Rsp *r,int track,const char *name,int loop,float alpha,int additive,int queued,float delay) {
    Animation *a=r->data->findAnimation(name); if (!a || track<0 || track>31) return 0;
    TrackEntry &entry=queued ? r->state->addAnimation(track,*a,loop,delay) : r->state->setAnimation(track,*a,loop);
    entry.setAlpha(alpha); entry.setAdditive(additive); return 1;
}
API void rsp_clear(Rsp *r,int track,float mix) {
    if (track<0) { r->state->clearTracks(); r->skeleton->setupPose(); }
    else if (track<=31) r->state->setEmptyAnimation(track,mix);
}
API int rsp_empty(Rsp *r,int track,float mix,int queued,float delay) {
    if (track<0 || track>31) return 0;
    if (queued) r->state->addEmptyAnimation(track,mix,delay); else r->state->setEmptyAnimation(track,mix);
    return 1;
}
typedef void (BoneLocal::*Setter)(float);
static Setter setters[]={&BoneLocal::setX,&BoneLocal::setY,&BoneLocal::setRotation,&BoneLocal::setScaleX,&BoneLocal::setScaleY,&BoneLocal::setShearX,&BoneLocal::setShearY};
static void local_values(BoneLocal &p,float *out) {
    out[0]=p.getX(); out[1]=p.getY(); out[2]=p.getRotation(); out[3]=p.getScaleX();
    out[4]=p.getScaleY(); out[5]=p.getShearX(); out[6]=p.getShearY();
}
API int rsp_override(Rsp *r,const char *name,int mask,const float *values) {
    Bone *bone=r->skeleton->findBone(name); if (!bone) return 0;
    int index=bone->getData().getIndex();
    size_t i=0; for (;i<r->overrides.size();i++) if(r->overrides[i].bone==index) break;
    if (i==r->overrides.size()) r->overrides.push_back(RspOverride{});
    RspOverride &o=r->overrides[i];
    float setup[7]; local_values(bone->getData().getSetupPose(),setup);
    for (int j=0;j<7;j++) if ((o.mask & ~mask)&(1<<j)) (bone->getPose().*setters[j])(setup[j]);
    o.bone=index; o.mask=mask; memcpy(o.value,values,7*sizeof(float)); return 1;
}
API int rsp_bone(Rsp *r,const char *name,float *out) {
    Bone *b=r->skeleton->findBone(name); if (!b) return 0;
    BonePose &p=b->getAppliedPose(); BonePose &local=b->getPose();
    out[0]=p.getWorldX(); out[1]=p.getWorldY(); out[2]=local.getX(); out[3]=local.getY(); out[4]=local.getRotation(); return 1;
}
API int rsp_bone_matrix(Rsp *r,const char *name,float *out) {
    Bone *b=r->skeleton->findBone(name); if (!b) return 0;
    BonePose &p=b->getAppliedPose();
    out[0]=p.getA(); out[1]=p.getB(); out[2]=p.getC(); out[3]=p.getD(); out[4]=p.getWorldX(); out[5]=p.getWorldY(); return 1;
}
API void rsp_update(Rsp *r,float delta) {
    r->skeleton->update(delta); r->state->update(delta); r->state->apply(*r->skeleton);
    for (const RspOverride &o:r->overrides) {
        BonePose &pose=r->skeleton->getBones()[o.bone]->getPose();
        for(int j=0;j<7;j++) if(o.mask&(1<<j)) (pose.*setters[j])(o.value[j]);
    }
    r->skeleton->updateWorldTransform(Physics_Update);
}
API int rsp_draw(Rsp *r,float scale,float originX,float originY) {
    RenderCommand *command=r->renderer.render(*r->skeleton);
    float minX=1e30f,minY=1e30f,maxX=-1e30f,maxY=-1e30f;
    r->batchCount=0;
    for (;command;command=command->next) {
        if (command->numVertices<=0 || command->numIndices<=0) continue;
        if (r->batchCount==(int)r->buffers.size()) r->buffers.emplace_back();
        Buffers &buf=r->buffers[r->batchCount++]; RspBatch &b=buf.batch;
        b.page=(int)(intptr_t)command->texture-1; b.blend=(int)command->blendMode;
        b.vertices=command->numVertices; b.indices=command->numIndices;
        buf.xy.resize(b.vertices*2); buf.attributes.resize(b.vertices*9); buf.triangles.resize(b.indices);
        for(int i=0;i<b.vertices;i++) {
            float x=originX+command->positions[i*2]*scale, y=originY-command->positions[i*2+1]*scale;
            buf.xy[i*2]=x; buf.xy[i*2+1]=y;
            minX=std::min(minX,x); minY=std::min(minY,y); maxX=std::max(maxX,x); maxY=std::max(maxY,y);
            uint32_t color=command->colors[i], dark=command->darkColors[i]; float alpha=(color>>24)/255.f;
            float *a=&buf.attributes[i*9]; a[0]=command->uvs[i*2]; a[1]=command->uvs[i*2+1];
            a[2]=((color>>16)&255)/255.f*alpha; a[3]=((color>>8)&255)/255.f*alpha; a[4]=(color&255)/255.f*alpha; a[5]=alpha;
            a[6]=((dark>>16)&255)/255.f*alpha; a[7]=((dark>>8)&255)/255.f*alpha; a[8]=(dark&255)/255.f*alpha;
        }
        for(int i=0;i<b.indices;i++) buf.triangles[i]=command->indices[i];
        b.xy=buf.xy.data(); b.attributes=buf.attributes.data(); b.triangles=buf.triangles.data();
        b.vertexCapacity=b.vertices; b.indexCapacity=b.indices;
    }
    r->bounds[0]=minX; r->bounds[1]=minY; r->bounds[2]=maxX; r->bounds[3]=maxY;
    return r->batchCount;
}
API RspBatch *rsp_batch(Rsp *r,int i) { return i>=0 && i<r->batchCount ? &r->buffers[i].batch : nullptr; }
API void rsp_bounds(Rsp *r,float *out) { memcpy(out,r->bounds,4*sizeof(float)); }
API int rsp_events(Rsp *r,RspEvent *out,int capacity) {
    int count=std::min(capacity,(int)r->events.size());
    if (count) memcpy(out,r->events.data(),count*sizeof(RspEvent));
    r->events.erase(r->events.begin(),r->events.begin()+count); return count;
}
