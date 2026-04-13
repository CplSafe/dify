import ImageGallery from '@/app/components/base/image-gallery'
import { getRenderableImageParagraphChildren, hasBlockMediaChild, hasImageChild } from './utils'

const Paragraph = (paragraph: any) => {
  const { node }: any = paragraph
  const children_node = node.children
  const hasImage = hasImageChild(children_node)
  const hasBlockMedia = hasBlockMediaChild(children_node)

  if (hasImage) {
    if (children_node[0]?.tagName === 'img') {
      const remainingChildren = getRenderableImageParagraphChildren(paragraph.children).slice(1)

      return (
        <div className="markdown-img-wrapper">
          <ImageGallery srcs={[children_node[0].properties.src]} variant="markdown" />
          {remainingChildren.length > 0
            ? <div className="mt-2">{remainingChildren}</div>
            : null}
        </div>
      )
    }
    return <div className="markdown-p">{paragraph.children}</div>
  }

  if (hasBlockMedia)
    return <div className="markdown-p">{paragraph.children}</div>

  return <p>{paragraph.children}</p>
}

export default Paragraph
