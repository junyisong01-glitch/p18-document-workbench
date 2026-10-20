/* Geometry from the guarded backend only. No page guessing or text rewriting. */
(function(root){
 function paint(container,url,rects,alt,className='highlight-page'){
  const doc=container.ownerDocument,wrapper=doc.createElement('div'),image=doc.createElement('img');
  wrapper.className=className;image.alt=alt;image.src=url;wrapper.append(image);
  for(const box of rects||[]){if(!Array.isArray(box)||box.length!==4||!box.every(Number.isFinite)||box[0]<0||box[1]<0||box[2]>1||box[3]>1||box[2]<=box[0]||box[3]<=box[1])continue;const mark=doc.createElement('span');mark.className='original-highlight';mark.setAttribute('aria-hidden','true');Object.assign(mark.style,{left:box[0]*100+'%',top:box[1]*100+'%',width:(box[2]-box[0])*100+'%',height:(box[3]-box[1])*100+'%'});wrapper.append(mark);}
  container.replaceChildren(wrapper);return {image,wrapper};
 }
 function score(value){return typeof value==='number'&&Number.isFinite(value)?value.toFixed(4):'未提供';}
 root.P18SourcePreview={paint,score};
})(typeof window==='undefined'?module.exports:window);
