#ifndef BDN_ANDROID_ScrollViewCore_H_
#define BDN_ANDROID_ScrollViewCore_H_

#include <bdn/ScrollView.h>
#include <bdn/IScrollViewCore.h>
#include <bdn/ScrollViewLayoutHelper.h>
#include <bdn/java/NativeWeakPointer.h>
#include <bdn/android/ViewCore.h>
#include <bdn/android/JNativeScrollViewManager.h>
#include <bdn/android/IParentViewCore.h>
#include <bdn/android/JViewGroup.h>
#include <bdn/android/JNativeScrollViewManager.h>

namespace bdn
{
    namespace android
    {

        class ScrollViewCore : public ViewCore,
                               BDN_IMPLEMENTS IScrollViewCore,
                               BDN_IMPLEMENTS IParentViewCore
        {
          private:
            static P<JNativeScrollViewManager>
            _createNativeScrollViewManager(ScrollView *pOuter)
            {
                // we need to know the context to create the view.
                // If we have a parent then we can get that from the parent's
                // core.
                P<View> pParent = pOuter->getParentView();
                if (pParent == nullptr)
                    throw ProgrammingError(
                        "ScrollViewCore instance requested for a ScrollView "
                        "that does not have a parent.");

                P<ViewCore> pParentCore =
                    cast<ViewCore>(pParent->getViewCore());
                if (pParentCore == nullptr)
                    throw ProgrammingError(
                        "ScrollViewCore instance requested for a ScrollView "
                        "with core-less parent.");

                JContext context = pParentCore->getJView().getContext();

                P<JNativeScrollViewManager> pMan =
                    newObj<JNativeScrollViewManager>(context);

                return pMan;
            }

          public:
            ScrollViewCore(ScrollView *pOuter)
                : ScrollViewCore(pOuter, _createNativeScrollViewManager(pOuter))
            {}

          private:
            ScrollViewCore(ScrollView *pOuter, P<JNativeScrollViewManager> pMan)
                : ViewCore(pOuter, newObj<JView>(pMan->getWrapperView()))
            {
                _pMan = pMan;

                // inside the scroll view we have a NativeViewGroup object as
                // the glue between our layout system and that of android. That
                // allows us to position the content view manually. It also
                // ensures that the parent of the content view is a
                // NativeViewGroup, which is important because we assume that
                // that is the case in some places.
                _pContentParent =
                    newObj<JNativeViewGroup>(pMan->getContentParent());

                setVerticalScrollingEnabled(pOuter->verticalScrollingEnabled());
                setHorizontalScrollingEnabled(
                    pOuter->horizontalScrollingEnabled());
            }

          public:
            void setHorizontalScrollingEnabled(const bool &enabled) override
            {
                // nothing to do - we get this directly from the outer window
            }

            void setVerticalScrollingEnabled(const bool &enabled) override
            {
                // nothing to do - we get this directly from the outer window
            }

            Size calcPreferredSize(
                const Size &availableSpace = Size::none()) const override
            {
                P<ScrollView> pOuter =
                    cast<ScrollView>(getOuterViewIfStillAttached());
                if (pOuter != nullptr) {
                    // note that the scroll bars are overlays and do not take up
                    // any layout space.
                    ScrollViewLayoutHelper helper(0, 0);

                    return helper.calcPreferredSize(pOuter, availableSpace);
                } else
                    return Size(0, 0);
            }

            void layout() override
            {
                P<ScrollView> pOuterView =
                    cast<ScrollView>(getOuterViewIfStillAttached());
                if (pOuterView != nullptr) {
                    // note that the scroll bars are overlays and do not take up
                    // any layout space.
                    ScrollViewLayoutHelper helper(0, 0);

                    Size scrollViewSize = pOuterView->size();

                    helper.calcLayout(pOuterView, scrollViewSize);

                    Size scrolledAreaSize = helper.getScrolledAreaSize();

                    double uiScaleFactor = getUiScaleFactor();

                    // resize the content parent to the scrolled area size.
                    // That causes the content parent to get that size the next
                    // time and android layout happens.
                    _pContentParent->setSize(
                        std::lround(scrolledAreaSize.width * uiScaleFactor),
                        std::lround(scrolledAreaSize.height * uiScaleFactor));

                    // now arrange the content view inside the content parent
                    Rect contentBounds = helper.getContentViewBounds();

                    P<View> pContentView = pOuterView->getContentView();
                    if (pContentView != nullptr)
                        pContentView->adjustAndSetBounds(contentBounds);

                    // we must call _pContentParent->requestLayout because we
                    // have to clear its measure cache. Otherwise the changes
                    // might not take effect.
                    _pContentParent->requestLayout();

                    updateVisibleClientRect();
                }
            }

            void scrollClientRectToVisible(const Rect &clientRect) override
            {
                int visibleLeft = _pMan->getScrollX();
                int visibleTop = _pMan->getScrollY();
                int visibleWidth = _pMan->getWidth();
                int visibleHeight = _pMan->getHeight();
                int visibleRight = visibleLeft + visibleWidth;
                int visibleBottom = visibleTop + visibleHeight;

                int clientWidth = _pContentParent->getWidth();
                int clientHeight = _pContentParent->getHeight();

                double uiScaleFactor = getUiScaleFactor();

                int targetLeft;
                int targetRight;
                if (std::isfinite(clientRect.x)) {
                    targetLeft = std::lround(clientRect.x * uiScaleFactor);
                    targetRight = targetLeft +
                                  std::lround(clientRect.width * uiScaleFactor);
                } else {
                    if (clientRect.x > 0)
                        targetLeft = clientWidth;
                    else
                        targetLeft = 0;

                    targetRight = targetLeft;
                }

                int targetTop;
                int targetBottom;
                if (std::isfinite(clientRect.y)) {
                    targetTop = std::lround(clientRect.y * uiScaleFactor);
                    targetBottom = targetTop + std::lround(clientRect.height *
                                                           uiScaleFactor);
                } else {
                    if (clientRect.y > 0)
                        targetTop = clientHeight;
                    else
                        targetTop = 0;

                    targetBottom = targetTop;
                }

                // first, clip the target rect to the client area.
                // This also automatically gets rid of infinity target positions
                // (which are allowed)
                if (targetLeft > clientWidth)
                    targetLeft = clientWidth;
                if (targetRight > clientWidth)
                    targetRight = clientWidth;
                if (targetTop > clientHeight)
                    targetTop = clientHeight;
                if (targetBottom > clientHeight)
                    targetBottom = clientHeight;

                if (targetLeft < 0)
                    targetLeft = 0;
                if (targetRight < 0)
                    targetRight = 0;
                if (targetTop < 0)
                    targetTop = 0;
                if (targetBottom < 0)
                    targetBottom = 0;

                // there is a special case if the target rect is bigger than the
                // viewport. In that case the desired end position is ambiguous:
                // any sub-rect of viewport size inside the specified target
                // rect would be "as good as possible". The documentation for
                // scrollClientRectToVisible resolves this ambiguity by
                // requiring that we scroll the minimal amount. So we want the
                // new visible rect to be as close to the old one as possible.

                // Since we specify the scroll position directly, we need to
                // handle this case on our side.

                if (targetRight - targetLeft > visibleWidth) {
                    if (visibleLeft >= targetLeft &&
                        visibleRight <= targetRight) {
                        // The current visible rect is already fully inside the
                        // target rect. In this case we do not want to move the
                        // scroll position at all. So set the target rect to the
                        // current view port rect
                        targetLeft = visibleLeft;
                        targetRight = visibleRight;
                    } else {
                        // shrink the target rect so that it matches the
                        // viewport width. We want to shrink towards the edge
                        // that is closest to the current visible rect. Note
                        // that the width of the visible rect is smaller than
                        // the target width and that the visible rect is not
                        // fully inside the target rect. So one of the target
                        // rect edges has to be closer than the other.

                        int distanceLeft = std::abs(targetLeft - visibleLeft);
                        int distanceRight =
                            std::abs(targetRight - visibleRight);

                        if (distanceLeft < distanceRight) {
                            // the left edge of the target rect is closer to the
                            // current visible rect than the right edge. So we
                            // want to move towards the left.
                            targetRight = targetLeft + visibleWidth;
                        } else {
                            // move towards the right edge
                            targetLeft = targetRight - visibleWidth;
                        }
                    }
                }

                if (targetBottom - targetTop > visibleHeight) {
                    if (visibleTop >= targetTop &&
                        visibleBottom <= targetBottom) {
                        targetTop = visibleTop;
                        targetBottom = visibleBottom;
                    } else {
                        int distanceTop = std::abs(targetTop - visibleTop);
                        int distanceBottom =
                            std::abs(targetBottom - visibleBottom);

                        if (distanceTop < distanceBottom)
                            targetBottom = targetTop + visibleHeight;
                        else
                            targetTop = targetBottom - visibleHeight;
                    }
                }

                if (targetLeft < 0)
                    targetLeft = 0;
                if (targetRight < 0)
                    targetRight = 0;
                if (targetTop < 0)
                    targetTop = 0;
                if (targetBottom < 0)
                    targetBottom = 0;

                int scrollX = visibleLeft;
                int scrollY = visibleTop;

                if (targetRight > visibleRight)
                    scrollX = targetRight - visibleWidth;
                if (targetLeft < visibleLeft)
                    scrollX = targetLeft;

                if (targetBottom > visibleBottom)
                    scrollY = targetBottom - visibleHeight;
                if (targetTop < visibleTop)
                    scrollY = targetTop;

                _pMan->smoothScrollTo(scrollX, scrollY);
            }

            double getUiScaleFactor() const override
            {
                return ViewCore::getUiScaleFactor();
            }

            void addChildJView(JView childJView) override
            {
                if (!_currContentJView.isNull_())
                    _pContentParent->removeView(_currContentJView);

                _currContentJView = childJView;
                _pContentParent->addView(childJView);
            }

            void removeChildJView(JView childJView) override
            {
                _pContentParent->removeView(childJView);
            }

            /** Used internally - do not call.*/
            void _scrollChange(int scrollX, int scrollY, int oldScrollX,
                               int oldScrollY)
            {
                updateVisibleClientRect();
            }

          private:
            void updateVisibleClientRect()
            {
                P<ScrollView> pOuter =
                    cast<ScrollView>(getOuterViewIfStillAttached());
                if (pOuter != nullptr) {
                    double uiScaleFactor = getUiScaleFactor();

                    Rect visibleRect(_pMan->getScrollX() / uiScaleFactor,
                                     _pMan->getScrollY() / uiScaleFactor,
                                     _pMan->getWidth() / uiScaleFactor,
                                     _pMan->getHeight() / uiScaleFactor);

                    pOuter->_setVisibleClientRect(visibleRect);
                }
            }

            P<JNativeScrollViewManager> _pMan;
            P<JNativeViewGroup> _pContentParent;

            JView _currContentJView;
        };
    }
}

#endif
