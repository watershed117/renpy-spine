/* Ren'Py bridge to the official Spine 3.8 C runtime with attachment fix.
 * See vendor/LICENSE for the Spine runtime license. Bridge ABI is versioned.
 */
#include <spine/spine.h>
#include <spine/extension.h>
#include <stdint.h>
#include <stdio.h>
#include <stddef.h>
#include <math.h>

#ifdef _WIN32
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif

#define RSP_ABI 1
#define ATTR 9 /* UV, premultiplied light RGBA, premultiplied dark RGB */
#define MAX_EVENTS 256

typedef struct {
    int page, blend, vertices, indices;
    float *xy, *attributes;
    uint32_t *triangles;
    int vertexCapacity, indexCapacity;
} RspBatch;

typedef struct {
    int type, track, integer;
    float time, number, volume, balance;
    char name[192], text[512], audio[384];
} RspEvent;

typedef struct {
    int bone, mask;
    float value[7];
} RspOverride;

typedef struct {
    spAtlas *atlas;
    spSkeletonData *data;
    spSkeleton *skeleton;
    spAnimationStateData *mix;
    spAnimationState *state;
    spSkeletonClipping *clip;
    RspBatch *batches;
    int batchCount, batchCapacity;
    float *world;
    int worldCapacity;
    RspOverride *overrides;
    int overrideCount;
    RspEvent events[MAX_EVENTS];
    int eventCount;
    int eventsDropped;
    float bounds[4];
} Rsp;

static void copy_text(char *dst, const char *src, size_t size) {
    snprintf(dst, size, "%s", src ? src : "");
}

/* Atlas dimensions are in the atlas. Texture decoding belongs to Ren'Py.
 * Assets arrive as bytes through renpy.open_file, including when in an RPA/APK.
 */
void _spAtlasPage_createTexture(spAtlasPage *page, const char *path) { (void)page; (void)path; }
void _spAtlasPage_disposeTexture(spAtlasPage *page) { (void)page; }
char *_spUtil_readFile(const char *path, int *length) { (void)path; *length=0; return NULL; }

static void listener(spAnimationState *state, spEventType type, spTrackEntry *entry, spEvent *event) {
    Rsp *r = state->rendererObject;
    RspEvent *out;
    if (!r || (type != SP_ANIMATION_EVENT && type != SP_ANIMATION_COMPLETE)) return;
    if (r->eventCount == MAX_EVENTS) { r->eventsDropped++; return; }
    out = &r->events[r->eventCount++];
    memset(out, 0, sizeof(*out));
    out->type=type; out->track=entry->trackIndex;
    if (event) {
        out->time=event->time; out->integer=event->intValue; out->number=event->floatValue;
        out->volume=event->volume; out->balance=event->balance;
        copy_text(out->name,event->data->name,sizeof(out->name));
        copy_text(out->text,event->stringValue,sizeof(out->text));
        copy_text(out->audio,event->data->audioPath,sizeof(out->audio));
    } else copy_text(out->name,entry->animation->name,sizeof(out->name));
}

API int rsp_abi(void) { return RSP_ABI; }
API void rsp_dispose(Rsp *r) {
    int i;
    if (!r) return;
    if (r->state) spAnimationState_dispose(r->state);
    if (r->mix) spAnimationStateData_dispose(r->mix);
    if (r->skeleton) spSkeleton_dispose(r->skeleton);
    if (r->data) spSkeletonData_dispose(r->data);
    if (r->atlas) spAtlas_dispose(r->atlas);
    if (r->clip) spSkeletonClipping_dispose(r->clip);
    for(i=0;i<r->batchCapacity;i++) {
        free(r->batches[i].xy); free(r->batches[i].attributes); free(r->batches[i].triangles);
    }
    free(r->batches); free(r->world); free(r->overrides); free(r);
}

/* Use actual atlas page dimensions for all rotation angles. This also avoids
 * the upstream 3.8 C mesh UV calculation's dimension inference for 270 degrees.
 * Vendor files remain identical; build-native.ps1 corrects attachment changes
 * in a generated AnimationState.c to clear stale mesh deformation.
 */
static void fix_mesh_uvs(spMeshAttachment *m) {
    spAtlasRegion *r = m->rendererObject;
    float tw=r->page->width, th=r->page->height;
    float u=r->u,v=r->v,w=r->originalWidth/tw,h=r->originalHeight/th;
    int i,n=m->super.worldVerticesLength;
    switch(r->degrees) {
        case 90:
            u-=(r->originalHeight-r->offsetY-r->height)/tw;
            v-=(r->originalWidth-r->offsetX-r->width)/th;
            w=r->originalHeight/tw; h=r->originalWidth/th;
            for(i=0;i<n;i+=2) {m->uvs[i]=u+m->regionUVs[i+1]*w;m->uvs[i+1]=v+(1-m->regionUVs[i])*h;}
            break;
        case 180:
            u-=(r->originalWidth-r->offsetX-r->width)/tw; v-=r->offsetY/th;
            for(i=0;i<n;i+=2) {m->uvs[i]=u+(1-m->regionUVs[i])*w;m->uvs[i+1]=v+(1-m->regionUVs[i+1])*h;}
            break;
        case 270:
            u-=r->offsetY/tw;v-=r->offsetX/th;w=r->originalHeight/tw;h=r->originalWidth/th;
            for(i=0;i<n;i+=2) {m->uvs[i]=u+(1-m->regionUVs[i+1])*w;m->uvs[i+1]=v+m->regionUVs[i]*h;}
            break;
        default:
            u-=r->offsetX/tw;v-=(r->originalHeight-r->offsetY-r->height)/th;
            for(i=0;i<n;i+=2) {m->uvs[i]=u+m->regionUVs[i]*w;m->uvs[i+1]=v+m->regionUVs[i+1]*h;}
    }
}

static void fix_region_uvs(spRegionAttachment *m) {
    spAtlasRegion *r=m->rendererObject;
    int turn=((r->degrees/90)%4+4)%4;
    float u=r->u,v=r->v;
    float u2=u+(turn%2?r->height:r->width)/(float)r->page->width;
    float v2=v+(turn%2?r->width:r->height)/(float)r->page->height;
    float corners[8]={u,v2,u,v,u2,v,u2,v2};
    int i;
    for(i=0;i<4;i++) {
        int source=(i-turn+4)%4;
        m->uvs[i*2]=corners[source*2];m->uvs[i*2+1]=corners[source*2+1];
    }
}

API Rsp *rsp_create(const char *atlas,int atlasLength,const unsigned char *data,int length,
                    int json,float scale,char *error,int errorLength) {
    Rsp *r=calloc(1,sizeof(*r));
    spAtlasPage *page;
    spSkeletonBinary *binary=NULL;
    spSkeletonJson *reader=NULL;
    int i, count=0;
    if (!r) {copy_text(error,"Out of memory",errorLength);return NULL;}
    spBone_setYDown(0);
    r->atlas=spAtlas_create(atlas,atlasLength,"",NULL);
    if (!r->atlas) {copy_text(error,"Invalid Spine 3.8 atlas",errorLength);goto fail;}
    for(page=r->atlas->pages;page;page=page->next) {
        if(page->width<=0 || page->height<=0) {copy_text(error,"Atlas requires explicit page size",errorLength);goto fail;}
        page->rendererObject=(void*)(intptr_t)count++;
    }
    if(json) {
        reader=spSkeletonJson_create(r->atlas);reader->scale=scale;
        r->data=spSkeletonJson_readSkeletonData(reader,(const char*)data);
        if(!r->data) copy_text(error,reader->error,errorLength);
        spSkeletonJson_dispose(reader);
    } else {
        binary=spSkeletonBinary_create(r->atlas);binary->scale=scale;
        r->data=spSkeletonBinary_readSkeletonData(binary,data,length);
        if(!r->data) copy_text(error,binary->error,errorLength);
        spSkeletonBinary_dispose(binary);
    }
    if(!r->data) goto fail;
    for(i=0;i<r->data->skinsCount;i++) {
        spSkinEntry *e=spSkin_getAttachments(r->data->skins[i]);
        for(;e;e=e->next) {
            if(e->attachment->type==SP_ATTACHMENT_MESH || e->attachment->type==SP_ATTACHMENT_LINKED_MESH)
                fix_mesh_uvs((spMeshAttachment*)e->attachment);
            else if(e->attachment->type==SP_ATTACHMENT_REGION)
                fix_region_uvs((spRegionAttachment*)e->attachment);
        }
    }
    r->skeleton=spSkeleton_create(r->data);
    r->mix=spAnimationStateData_create(r->data);r->mix->defaultMix=0.2f;
    r->state=spAnimationState_create(r->mix);r->state->rendererObject=r;r->state->listener=listener;
    r->clip=spSkeletonClipping_create();
    spSkeleton_updateWorldTransform(r->skeleton);
    return r;
fail:
    rsp_dispose(r);return NULL;
}

API int rsp_animation_count(Rsp *r) {return r->data->animationsCount;}
API const char *rsp_animation_name(Rsp *r,int i) {return i>=0&&i<r->data->animationsCount?r->data->animations[i]->name:NULL;}
API float rsp_animation_duration(Rsp *r,int i) {return i>=0&&i<r->data->animationsCount?r->data->animations[i]->duration:0;}
API int rsp_bone_count(Rsp *r) {return r->data->bonesCount;}
API const char *rsp_bone_name(Rsp *r,int i) {return i>=0&&i<r->data->bonesCount?r->data->bones[i]->name:NULL;}
API int rsp_page_count(Rsp *r) {spAtlasPage*p;int n=0;for(p=r->atlas->pages;p;p=p->next)n++;return n;}
API const char *rsp_page_name(Rsp *r,int i) {spAtlasPage*p;for(p=r->atlas->pages;p;p=p->next)if(i--==0)return p->name;return NULL;}
API int rsp_skin(Rsp *r,const char *name) {return spSkeleton_setSkinByName(r->skeleton,name);}
API void rsp_default_mix(Rsp *r,float duration) {r->mix->defaultMix=duration;}
API int rsp_mix(Rsp *r,const char *a,const char *b,float duration) {
    if(!spSkeletonData_findAnimation(r->data,a)||!spSkeletonData_findAnimation(r->data,b))return 0;
    spAnimationStateData_setMixByName(r->mix,a,b,duration);return 1;
}
API int rsp_play(Rsp *r,int track,const char *name,int loop,float alpha,int additive,int queued,float delay) {
    spAnimation *a=spSkeletonData_findAnimation(r->data,name);spTrackEntry *entry;
    if(!a || track<0 || track>31)return 0;
    entry=queued?spAnimationState_addAnimation(r->state,track,a,loop,delay):spAnimationState_setAnimation(r->state,track,a,loop);
    entry->alpha=alpha;entry->mixBlend=additive?SP_MIX_BLEND_ADD:SP_MIX_BLEND_REPLACE;return 1;
}
API void rsp_clear(Rsp *r,int track,float mix) {
    if(track<0){spAnimationState_clearTracks(r->state);spSkeleton_setToSetupPose(r->skeleton);}
    else if(track<=31) spAnimationState_setEmptyAnimation(r->state,track,mix);
}
API int rsp_empty(Rsp *r,int track,float mix,int queued,float delay) {
    if(track<0||track>31)return 0;
    if(queued)spAnimationState_addEmptyAnimation(r->state,track,mix,delay);
    else spAnimationState_setEmptyAnimation(r->state,track,mix);
    return 1;
}
API int rsp_override(Rsp *r,const char *name,int mask,const float *values) {
    int index=spSkeleton_findBoneIndex(r->skeleton,name),i;
    RspOverride *o;
    if(index<0)return 0;
    for(i=0;i<r->overrideCount;i++)if(r->overrides[i].bone==index)break;
    if(i==r->overrideCount) {
        r->overrides=realloc(r->overrides,(++r->overrideCount)*sizeof(*o));
        memset(&r->overrides[i],0,sizeof(*o));
    }
    o=&r->overrides[i];
    if(o->mask & ~mask) {
        spBone *b=r->skeleton->bones[index];spBoneData *d=b->data;int j;
        float *fields[]={&b->x,&b->y,&b->rotation,&b->scaleX,&b->scaleY,&b->shearX,&b->shearY};
        float setup[]={d->x,d->y,d->rotation,d->scaleX,d->scaleY,d->shearX,d->shearY};
        for(j=0;j<7;j++)if((o->mask & ~mask)&(1<<j))*fields[j]=setup[j];
    }
    o->bone=index;o->mask=mask;memcpy(o->value,values,7*sizeof(float));return 1;
}
API int rsp_bone(Rsp *r,const char *name,float *out) {
    spBone *b=spSkeleton_findBone(r->skeleton,name);if(!b)return 0;
    out[0]=b->worldX;out[1]=b->worldY;out[2]=b->x;out[3]=b->y;out[4]=b->rotation;return 1;
}
/* Affine transform for input hit testing and procedural control. */
API int rsp_bone_matrix(Rsp *r,const char *name,float *out) {
    spBone *b=spSkeleton_findBone(r->skeleton,name);if(!b)return 0;
    out[0]=b->a;out[1]=b->b;out[2]=b->c;out[3]=b->d;
    out[4]=b->worldX;out[5]=b->worldY;return 1;
}
API void rsp_update(Rsp *r,float delta) {
    int i,j;
    spSkeleton_update(r->skeleton,delta);spAnimationState_update(r->state,delta);
    spAnimationState_apply(r->state,r->skeleton);
    for(i=0;i<r->overrideCount;i++) {
        RspOverride *o=&r->overrides[i];spBone *b=r->skeleton->bones[o->bone];
        float *fields[]={&b->x,&b->y,&b->rotation,&b->scaleX,&b->scaleY,&b->shearX,&b->shearY};
        for(j=0;j<7;j++)if(o->mask&(1<<j))*fields[j]=o->value[j];
    }
    spSkeleton_updateWorldTransform(r->skeleton);
}

static RspBatch *batch(Rsp *r,int page,int blend,int vertices,int indices) {
    RspBatch *b;
    if(!r->batchCount || r->batches[r->batchCount-1].page!=page || r->batches[r->batchCount-1].blend!=blend
       || r->batches[r->batchCount-1].vertices+vertices>60000) {
        if(r->batchCount==r->batchCapacity) {
            int old=r->batchCapacity;r->batchCapacity=old?old*2:16;
            r->batches=realloc(r->batches,r->batchCapacity*sizeof(*b));
            memset(r->batches+old,0,(r->batchCapacity-old)*sizeof(*b));
        }
        b=&r->batches[r->batchCount++];b->page=page;b->blend=blend;b->vertices=0;b->indices=0;
    } else b=&r->batches[r->batchCount-1];
    if(b->vertexCapacity<b->vertices+vertices) {
        b->vertexCapacity=(b->vertices+vertices)*2;
        b->xy=realloc(b->xy,b->vertexCapacity*2*sizeof(float));
        b->attributes=realloc(b->attributes,b->vertexCapacity*ATTR*sizeof(float));
    }
    if(b->indexCapacity<b->indices+indices) {
        b->indexCapacity=(b->indices+indices)*2;
        b->triangles=realloc(b->triangles,b->indexCapacity*sizeof(uint32_t));
    }
    return b;
}

API int rsp_draw(Rsp *r,float scale,float originX,float originY) {
    int i,j;float minX=1e30f,minY=1e30f,maxX=-1e30f,maxY=-1e30f;
    unsigned short quad[]={0,1,2,2,3,0};
    r->batchCount=0;
    for(i=0;i<r->skeleton->slotsCount;i++) {
        spSlot *slot=r->skeleton->drawOrder[i];spAttachment *a=slot->attachment;
        spAtlasRegion *region;spColor *color;float *uv,*xy;unsigned short *triangles;
        int n,tn;float light[4],dark[3],alpha;RspBatch *b;
        if(!a || !slot->bone->active){spSkeletonClipping_clipEnd(r->clip,slot);continue;}
        if(a->type==SP_ATTACHMENT_CLIPPING) {spSkeletonClipping_clipStart(r->clip,slot,(spClippingAttachment*)a);continue;}
        if(a->type==SP_ATTACHMENT_REGION)n=8;
        else if(a->type==SP_ATTACHMENT_MESH || a->type==SP_ATTACHMENT_LINKED_MESH)n=((spMeshAttachment*)a)->super.worldVerticesLength;
        else {spSkeletonClipping_clipEnd(r->clip,slot);continue;}
        if(n>r->worldCapacity) {r->worldCapacity=n*2;r->world=realloc(r->world,r->worldCapacity*sizeof(float));}
        xy=r->world;
        if(a->type==SP_ATTACHMENT_REGION) {
            spRegionAttachment *m=(spRegionAttachment*)a;
            spRegionAttachment_computeWorldVertices(m,slot->bone,xy,0,2);
            region=m->rendererObject;color=&m->color;uv=m->uvs;triangles=quad;tn=6;
        } else {
            spMeshAttachment *m=(spMeshAttachment*)a;
            spVertexAttachment_computeWorldVertices(&m->super,slot,0,n,xy,0,2);
            region=m->rendererObject;color=&m->color;uv=m->uvs;triangles=m->triangles;tn=m->trianglesCount;
        }
        alpha=r->skeleton->color.a*slot->color.a*color->a;
        if(alpha<=0){spSkeletonClipping_clipEnd(r->clip,slot);continue;}
        if(spSkeletonClipping_isClipping(r->clip)) {
            spSkeletonClipping_clipTriangles(r->clip,xy,n,triangles,tn,uv,2);
            xy=r->clip->clippedVertices->items;n=r->clip->clippedVertices->size;
            uv=r->clip->clippedUVs->items;triangles=r->clip->clippedTriangles->items;tn=r->clip->clippedTriangles->size;
        }
        if(n&&tn) {
            light[0]=r->skeleton->color.r*slot->color.r*color->r*alpha;
            light[1]=r->skeleton->color.g*slot->color.g*color->g*alpha;
            light[2]=r->skeleton->color.b*slot->color.b*color->b*alpha;light[3]=alpha;
            dark[0]=slot->darkColor?slot->darkColor->r*alpha:0;
            dark[1]=slot->darkColor?slot->darkColor->g*alpha:0;
            dark[2]=slot->darkColor?slot->darkColor->b*alpha:0;
            b=batch(r,(int)(intptr_t)region->page->rendererObject,slot->data->blendMode,n/2,tn);
            for(j=0;j<n/2;j++) {
                int p=b->vertices+j;float *attr=b->attributes+p*ATTR;
                float x=originX+xy[j*2]*scale,y=originY-xy[j*2+1]*scale;
                b->xy[p*2]=x;b->xy[p*2+1]=y;
                if(x<minX)minX=x;if(y<minY)minY=y;if(x>maxX)maxX=x;if(y>maxY)maxY=y;
                attr[0]=uv[j*2];attr[1]=uv[j*2+1];memcpy(attr+2,light,4*sizeof(float));memcpy(attr+6,dark,3*sizeof(float));
            }
            for(j=0;j<tn;j++)b->triangles[b->indices+j]=triangles[j]+b->vertices;
            b->vertices+=n/2;b->indices+=tn;
        }
        spSkeletonClipping_clipEnd(r->clip,slot);
    }
    spSkeletonClipping_clipEnd2(r->clip);
    r->bounds[0]=minX;r->bounds[1]=minY;r->bounds[2]=maxX;r->bounds[3]=maxY;
    return r->batchCount;
}
API RspBatch *rsp_batch(Rsp *r,int i) {return i>=0&&i<r->batchCount?&r->batches[i]:NULL;}
API void rsp_bounds(Rsp *r,float *out) {memcpy(out,r->bounds,4*sizeof(float));}
API int rsp_events(Rsp *r,RspEvent *out,int capacity) {
    int n=capacity<r->eventCount?capacity:r->eventCount;
    memcpy(out,r->events,n*sizeof(*out));r->eventCount-=n;
    memmove(r->events,r->events+n,r->eventCount*sizeof(*out));return n;
}

/* Portable snapshot of track chains and queues. No addresses enter a save.
 * TrackEntry scalar fields are all fixed-width int/float in the 3.8 runtime.
 */
typedef struct {
    int32_t track, animation, kind;
    int32_t loop,holdPrevious;
    float eventThreshold,attachmentThreshold,drawOrderThreshold;
    float animationStart,animationEnd,animationLast,nextAnimationLast;
    float delay,trackTime,trackLast,nextTrackLast,trackEnd,timeScale;
    float alpha,mixTime,mixDuration,interruptAlpha,totalAlpha;
    int32_t mixBlend;
} RspTrack;
#define SNAP_FIELDS(F) F(loop) F(holdPrevious) F(eventThreshold) F(attachmentThreshold) F(drawOrderThreshold) \
 F(animationStart) F(animationEnd) F(animationLast) F(nextAnimationLast) F(delay) F(trackTime) F(trackLast) \
 F(nextTrackLast) F(trackEnd) F(timeScale) F(alpha) F(mixTime) F(mixDuration) F(interruptAlpha) F(totalAlpha) F(mixBlend)

static int save_entry(Rsp *r,spTrackEntry *entry,int track,int kind,RspTrack *out,int count) {
    int i;RspTrack *s;
    if(entry->mixingFrom)count=save_entry(r,entry->mixingFrom,track,0,out,count);
    if(out) {
        s=&out[count];memset(s,0,sizeof(*s));s->track=track;s->kind=kind;s->animation=-1;
        for(i=0;i<r->data->animationsCount;i++)if(r->data->animations[i]==entry->animation)s->animation=i;
#define SAVE_FIELD(f) s->f=entry->f;
        SNAP_FIELDS(SAVE_FIELD)
#undef SAVE_FIELD
    }
    count++;
    /* A queued entry that became current is still referenced by its mixing
     * predecessor's next pointer. Only serialize the live queue once, from
     * the current entry, otherwise next -> mixingFrom forms a recursion cycle.
     */
    if(entry->next && !entry->mixingTo)count=save_entry(r,entry->next,track,1,out,count);
    return count;
}
API int rsp_snapshot(Rsp *r,RspTrack *out) {
    int i,n=0;for(i=0;i<r->state->tracksCount;i++)if(r->state->tracks[i])n=save_entry(r,r->state->tracks[i],i,0,out,n);return n;
}
API int rsp_restore(Rsp *r,const RspTrack *data,int count) {
    int i;spTrackEntry *e;
    /* Validate the complete snapshot before mutating state. */
    if(count<0||count>4096)return 0;
    for(i=0;i<count;i++)if(data[i].track<0||data[i].track>31||data[i].animation< -1||data[i].animation>=r->data->animationsCount)return 0;
    r->state->listener=NULL;spAnimationState_clearTracks(r->state);spSkeleton_setToSetupPose(r->skeleton);
    for(i=0;i<count;i++) {
        const RspTrack *s=&data[i];
        if(s->animation<0) e=s->kind?spAnimationState_addEmptyAnimation(r->state,s->track,s->mixDuration,s->delay):spAnimationState_setEmptyAnimation(r->state,s->track,s->mixDuration);
        else e=s->kind?spAnimationState_addAnimation(r->state,s->track,r->data->animations[s->animation],s->loop,s->delay):spAnimationState_setAnimation(r->state,s->track,r->data->animations[s->animation],s->loop);
#define LOAD_FIELD(f) e->f=s->f;
        SNAP_FIELDS(LOAD_FIELD)
#undef LOAD_FIELD
    }
    spAnimationState_apply(r->state,r->skeleton);spSkeleton_updateWorldTransform(r->skeleton);
    r->eventCount=0;r->state->listener=listener;return 1;
}
API int rsp_track_size(void) {return sizeof(RspTrack);}
