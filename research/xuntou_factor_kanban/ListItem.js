import{at as D,bv as m,W as p,U as s,V as v,X as t,aT as M,aU as H,d as h,Z as j,az as B,_ as u,a2 as E,a3 as I,q as T,a7 as V,G as n,J as K,K as N,L as O}from"./index.982edc77.js";const S=o=>{const{textColor2:r,cardColor:e,modalColor:l,popoverColor:d,dividerColor:a,borderRadius:b,fontSize:i,hoverColor:c}=o;return{textColor:r,color:e,colorHover:c,colorModal:l,colorHoverModal:m(l,c),colorPopover:d,colorHoverPopover:m(d,c),borderColor:a,borderColorModal:m(l,a),borderColorPopover:m(d,a),borderRadius:b,fontSize:i}},U={name:"List",common:D,self:S},q=U,G=p([s("list",`
 --n-merged-border-color: var(--n-border-color);
 --n-merged-color: var(--n-color);
 --n-merged-color-hover: var(--n-color-hover);
 margin: 0;
 font-size: var(--n-font-size);
 transition:
 background-color .3s var(--n-bezier),
 color .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
 padding: 0;
 list-style-type: none;
 color: var(--n-text-color);
 background-color: var(--n-merged-color);
 `,[v("show-divider",[s("list-item",[p("&:not(:last-child)",[t("divider",`
 background-color: var(--n-merged-border-color);
 `)])])]),v("clickable",[s("list-item",`
 cursor: pointer;
 `)]),v("bordered",`
 border: 1px solid var(--n-merged-border-color);
 border-radius: var(--n-border-radius);
 `),v("hoverable",[s("list-item",`
 border-radius: var(--n-border-radius);
 `,[p("&:hover",`
 background-color: var(--n-merged-color-hover);
 `,[t("divider",`
 background-color: transparent;
 `)])])]),v("bordered, hoverable",[s("list-item",`
 padding: 12px 20px;
 `),t("header, footer",`
 padding: 12px 20px;
 `)]),t("header, footer",`
 padding: 12px 0;
 box-sizing: border-box;
 transition: border-color .3s var(--n-bezier);
 `,[p("&:not(:last-child)",`
 border-bottom: 1px solid var(--n-merged-border-color);
 `)]),s("list-item",`
 position: relative;
 padding: 12px 0; 
 box-sizing: border-box;
 display: flex;
 flex-wrap: nowrap;
 align-items: center;
 transition:
 background-color .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
 `,[t("prefix",`
 margin-right: 20px;
 flex: 0;
 `),t("suffix",`
 margin-left: 20px;
 flex: 0;
 `),t("main",`
 flex: 1;
 `),t("divider",`
 height: 1px;
 position: absolute;
 bottom: 0;
 left: 0;
 right: 0;
 background-color: transparent;
 transition: background-color .3s var(--n-bezier);
 pointer-events: none;
 `)])]),M(s("list",`
 --n-merged-color-hover: var(--n-color-hover-modal);
 --n-merged-color: var(--n-color-modal);
 --n-merged-border-color: var(--n-border-color-modal);
 `)),H(s("list",`
 --n-merged-color-hover: var(--n-color-hover-popover);
 --n-merged-color: var(--n-color-popover);
 --n-merged-border-color: var(--n-border-color-popover);
 `))]),J=Object.assign(Object.assign({},u.props),{size:{type:String,default:"medium"},bordered:Boolean,clickable:Boolean,hoverable:Boolean,showDivider:{type:Boolean,default:!0}}),f=K("n-list"),X=h({name:"List",props:J,setup(o){const{mergedClsPrefixRef:r,inlineThemeDisabled:e,mergedRtlRef:l}=j(o),d=B("List",l,r),a=u("List","-list",G,q,o,r);E(f,{showDividerRef:I(o,"showDivider"),mergedClsPrefixRef:r});const b=T(()=>{const{common:{cubicBezierEaseInOut:c},self:{fontSize:g,textColor:x,color:C,colorModal:z,colorPopover:R,borderColor:$,borderColorModal:P,borderColorPopover:_,borderRadius:k,colorHover:w,colorHoverModal:L,colorHoverPopover:y}}=a.value;return{"--n-font-size":g,"--n-bezier":c,"--n-text-color":x,"--n-color":C,"--n-border-radius":k,"--n-border-color":$,"--n-border-color-modal":P,"--n-border-color-popover":_,"--n-color-modal":z,"--n-color-popover":R,"--n-color-hover":w,"--n-color-hover-modal":L,"--n-color-hover-popover":y}}),i=e?V("list",void 0,b,o):void 0;return{mergedClsPrefix:r,rtlEnabled:d,cssVars:e?void 0:b,themeClass:i==null?void 0:i.themeClass,onRender:i==null?void 0:i.onRender}},render(){var o;const{$slots:r,mergedClsPrefix:e,onRender:l}=this;return l==null||l(),n("ul",{class:[`${e}-list`,this.rtlEnabled&&`${e}-list--rtl`,this.bordered&&`${e}-list--bordered`,this.showDivider&&`${e}-list--show-divider`,this.hoverable&&`${e}-list--hoverable`,this.clickable&&`${e}-list--clickable`,this.themeClass],style:this.cssVars},r.header?n("div",{class:`${e}-list__header`},r.header()):null,(o=r.default)===null||o===void 0?void 0:o.call(r),r.footer?n("div",{class:`${e}-list__footer`},r.footer()):null)}}),Z=h({name:"ListItem",setup(){const o=N(f,null);return o||O("list-item","`n-list-item` must be placed in `n-list`."),{showDivider:o.showDividerRef,mergedClsPrefix:o.mergedClsPrefixRef}},render(){const{$slots:o,mergedClsPrefix:r}=this;return n("li",{class:`${r}-list-item`},o.prefix?n("div",{class:`${r}-list-item__prefix`},o.prefix()):null,o.default?n("div",{class:`${r}-list-item__main`},o):null,o.suffix?n("div",{class:`${r}-list-item__suffix`},o.suffix()):null,this.showDivider&&n("div",{class:`${r}-list-item__divider`}))}});export{X as N,Z as a,q as l,S as s};
