#include <bdn/init.h>
#include <bdn/Window.h>

#include <bdn/test.h>
#include <bdn/test/testView.h>
#include <bdn/test/MockButtonCore.h>
#include <bdn/test/MockWindowCore.h>

#include <bdn/Button.h>

using namespace bdn;

void testSizingWithContentView(P<bdn::test::ViewWithTestExtensions<Window>> pWindow,
                               P<bdn::test::MockUiProvider> pUiProvider, std::function<Size()> getSizeFunc)
{
    // we add a button as a content view
    P<Button> pButton = newObj<Button>();
    pButton->setLabel("HelloWorld");

    Margin buttonMargin;

    SECTION("noMargin")
    {
        // do nothing
    }

    SECTION("semMargin")
    {
        pButton->setMargin(UiMargin(UiLength::sem(1), UiLength::sem(2), UiLength::sem(3), UiLength::sem(4)));

        // 1 sem = 20 DIPs in our mock ui
        buttonMargin = Margin(20, 40, 60, 80);
    }

    SECTION("dipMargin")
    {
        pButton->setMargin(UiMargin(1, 2, 3, 4));

        buttonMargin = Margin(1, 2, 3, 4);
    }

    pWindow->setContentView(pButton);

    P<bdn::test::MockButtonCore> pButtonCore = cast<bdn::test::MockButtonCore>(pButton->getViewCore());

    // Sanity check. Verify the fake button size. 9.75 , 19.60 per character,
    // rounded to full 1/3 DIP pixels, plus 10x8 for border
    Size buttonSize(std::ceil(10 * 9.75 * 3) / 3 + 10, 19 + 2.0 / 3 + 8);
    REQUIRE_ALMOST_EQUAL(pButtonCore->calcPreferredSize(), buttonSize, Size(0.0000001, 0.0000001));

    // window border size is 20, 11, 12, 13 in our fake UI
    Margin windowBorder(20, 11, 12, 13);

    Size expectedSize = buttonSize + buttonMargin + windowBorder;

    // the sizing info will update asynchronously. So we need to do the
    // check async as well.
    CONTINUE_SECTION_WHEN_IDLE(getSizeFunc, expectedSize)
    {
        Size size = getSizeFunc();

        REQUIRE_ALMOST_EQUAL(size, expectedSize, Size(0.0000001, 0.0000001));
    };
}

TEST_CASE("Window", "[ui]")
{
    SECTION("View-base")
    bdn::test::testView<Window>();

    SECTION("Window-specific")
    {
        P<bdn::test::ViewTestPreparer<Window>> pPreparer = newObj<bdn::test::ViewTestPreparer<Window>>();

        P<bdn::test::ViewWithTestExtensions<Window>> pWindow = pPreparer->createView();

        P<bdn::test::MockWindowCore> pCore = cast<bdn::test::MockWindowCore>(pWindow->getViewCore());
        REQUIRE(pCore != nullptr);

        // continue testing after the async init has finished
        CONTINUE_SECTION_WHEN_IDLE(pPreparer, pWindow,
                                   pCore){// testView already tests the initialization of properties defined
                                          // in View. So we only have to test the Window-specific things here.
                                          SECTION("constructWindowSpecific"){REQUIRE(pCore->getTitleChangeCount() == 0);

        REQUIRE(pWindow->title() == "");
    }

    SECTION("changeWindowProperty")
    {
        SECTION("title")
        {
            bdn::test::_testViewOp(pWindow, pPreparer, [pWindow]() { pWindow->setTitle("hello"); },
                                   [pCore, pWindow] {
                                       REQUIRE(pCore->getTitleChangeCount() == 1);
                                       REQUIRE(pCore->getTitle() == "hello");
                                   },
                                   0 // should NOT cause a sizing info update, since the
                                     // title is not part of the "preferred size" calculation
                                     // should also not cause a parent layout update
            );
        }

        SECTION("contentView")
        {
            SECTION("set to !=null")
            {
                P<Button> pButton = newObj<Button>();
                bdn::test::_testViewOp(
                    pWindow, pPreparer, [pWindow, pButton]() { pWindow->setContentView(pButton); },
                    [pWindow, pButton] { REQUIRE(pWindow->getContentView() == cast<View>(pButton)); },
                    bdn::test::ExpectedSideEffect_::invalidateSizingInfo |
                        bdn::test::ExpectedSideEffect_::invalidateLayout
                    // should have caused a sizing info update and a layout
                    // update should not cause a parent layout update, since
                    // there is no parent
                );
            }

            SECTION("set to null")
            {
                SECTION("was null")
                {
                    // sanity check
                    REQUIRE(pWindow->getContentView() == nullptr);

                    bdn::test::_testViewOp(pWindow, pPreparer, [pWindow]() { pWindow->setContentView(nullptr); },
                                           [pWindow] { REQUIRE(pWindow->getContentView() == nullptr); },
                                           0 // this should not invalidate anything since the
                                             // property does not actually change
                    );
                }
                else
                {
                    // first make sure that there is a content view attached
                    // before the test runs
                    P<Button> pButton = newObj<Button>();

                    pWindow->setContentView(pButton);

                    CONTINUE_SECTION_WHEN_IDLE(pPreparer, pWindow, pCore)
                    {
                        // basically we only test here that there is no crash
                        // when the content view is set to null and that it does
                        // result in a sizing info update.
                        bdn::test::_testViewOp(pWindow, pPreparer, [pWindow]() { pWindow->setContentView(nullptr); },
                                               [pWindow] { REQUIRE(pWindow->getContentView() == nullptr); },
                                               bdn::test::ExpectedSideEffect_::invalidateSizingInfo |
                                                   bdn::test::ExpectedSideEffect_::invalidateLayout);
                    };
                }
            }
        }
    }

    SECTION("childParent")
    {
        P<Button> pChild = newObj<Button>();

        SECTION("setWhenAdded")
        {
            pWindow->setContentView(pChild);

            BDN_REQUIRE(pChild->getParentView() == cast<View>(pWindow));
        }

        SECTION("nullAfterDestroy")
        {
            {
                bdn::test::ViewTestPreparer<Window> preparer2;

                P<bdn::test::ViewWithTestExtensions<Window>> pWindow2 = preparer2.createView();

                pWindow2->setContentView(pChild);
            }

            // preparer2 is now gone, so the window is not referenced there
            // anymore. But there may still be a scheduled sizing info update
            // pending that holds a reference to the window. Since we want the
            // window to be destroyed, we do the remaining test asynchronously
            // after all pending operations are done.

            CONTINUE_SECTION_WHEN_IDLE_WITH([pChild]() { BDN_REQUIRE(pChild->getParentView() == nullptr); });
        }
    }

    SECTION("getChildList")
    {
        SECTION("empty")
        {
            List<P<View>> childList;
            pWindow->getChildViews(childList);

            REQUIRE(childList.empty());
        }

        SECTION("non-empty")
        {
            P<Button> pChild = newObj<Button>();
            pWindow->setContentView(pChild);

            List<P<View>> childList;
            pWindow->getChildViews(childList);

            REQUIRE(childList.size() == 1);
            REQUIRE(childList.front() == cast<View>(pChild));
        }
    }

    SECTION("removeAllChildViews")
    {
        SECTION("no content view")
        {
            pWindow->removeAllChildViews();

            List<P<View>> childList;
            pWindow->getChildViews(childList);

            REQUIRE(childList.empty());
        }

        SECTION("with content view")
        {
            P<Button> pChild = newObj<Button>();
            pWindow->setContentView(pChild);

            pWindow->removeAllChildViews();

            REQUIRE(pWindow->getContentView() == nullptr);
            REQUIRE(pChild->getParentView() == nullptr);

            List<P<View>> childList;
            pWindow->getChildViews(childList);

            REQUIRE(childList.empty());
        }
    }

    SECTION("sizing")
    {
        SECTION("noContentView")
        {
            // the mock window core reports border margins 20,11,12,13
            // and a minimum size of 100x32.
            // Since we do not have a content view we should get the min size
            // here.
            Size expectedSize(100, 32);

            SECTION("calcPreferredSize")
            REQUIRE(pWindow->calcPreferredSize() == expectedSize);
        }

        SECTION("withContentView")
        {
            SECTION("calcPreferredSize")
            testSizingWithContentView(pWindow, pPreparer->getUiProvider(),
                                      [pWindow]() { return pWindow->calcPreferredSize(); });
        }
    }

    SECTION("autoSize")
    {
        Point positionBefore = pWindow->position();
        Size sizeBefore = pWindow->size();

        pWindow->requestAutoSize();

        // auto-sizing is ALWAYS done asynchronously.
        // So nothing should have happened yet.

        REQUIRE(pWindow->position() == positionBefore);
        REQUIRE(pWindow->size() == sizeBefore);

        CONTINUE_SECTION_WHEN_IDLE_WITH([pWindow]() {
            REQUIRE(pWindow->position() == Point(0, 0));
            REQUIRE(pWindow->size() == Size(100, 32));
        });
    }

    SECTION("center")
    {
        pWindow->adjustAndSetBounds(Rect(0, 0, 200, 200));

        pWindow->requestCenter();

        // centering is ALWAYS done asynchronously.
        // So nothing should have happened yet.

        REQUIRE(pWindow->position() == Point(0, 0));
        REQUIRE(pWindow->size() == Size(200, 200));

        CONTINUE_SECTION_WHEN_IDLE(pWindow)
        {
            // the work area of our mock window is 100,100 800x800
            REQUIRE(pWindow->position() == Point(100 + (800 - 200) / 2, 100 + (800 - 200) / 2));

            REQUIRE(pWindow->size() == Size(200, 200));
        };
    }

    SECTION("contentView aligned on full pixels")
    {
        P<Button> pChild = newObj<Button>();
        pChild->setLabel("hello");

        SECTION("weird child margin")
        pChild->setMargin(UiMargin(0.12345678));

        SECTION("weird window padding")
        pWindow->setPadding(UiMargin(0.12345678));

        pWindow->setContentView(pChild);

        CONTINUE_SECTION_WHEN_IDLE(pChild, pWindow)
        {
            // the mock views we use have 3 pixels per dip
            double pixelsPerDip = 3;

            Point pos = pChild->position();

            REQUIRE_ALMOST_EQUAL(pos.x * pixelsPerDip, std::round(pos.x * pixelsPerDip), 0.000001);
            REQUIRE_ALMOST_EQUAL(pos.y * pixelsPerDip, std::round(pos.y * pixelsPerDip), 0.000001);

            Size size = pChild->size();
            REQUIRE_ALMOST_EQUAL(size.width * pixelsPerDip, std::round(size.width * pixelsPerDip), 0.000001);
            REQUIRE_ALMOST_EQUAL(size.height * pixelsPerDip, std::round(size.height * pixelsPerDip), 0.000001);
        };
    }

    SECTION("content view detached before destruction begins")
    {
        P<Button> pChild = newObj<Button>();
        pWindow->setContentView(pChild);

        struct LocalTestData_ : public Base
        {
            bool destructorRun = false;
            int childParentStillSet = -1;
            int childStillChild = -1;
        };

        P<LocalTestData_> pData = newObj<LocalTestData_>();

        pWindow->setDestructFunc([pData, pChild](bdn::test::ViewWithTestExtensions<Window> *pWin) {
            pData->destructorRun = true;
            pData->childParentStillSet = (pChild->getParentView() != nullptr) ? 1 : 0;
            pData->childStillChild = (pWin->getContentView() != nullptr) ? 1 : 0;
        });

        BDN_CONTINUE_SECTION_WHEN_IDLE(pData, pChild)
        {
            // All test objects should have been destroyed by now.
            // First verify that the destructor was even called.
            REQUIRE(pData->destructorRun);

            // now verify what we actually want to test: that the
            // content view's parent was set to null before the destructor
            // of the parent was called.
            REQUIRE(pData->childParentStillSet == 0);

            // the child should also not be a child of the parent
            // from the parent's perspective anymore.
            REQUIRE(pData->childStillChild == 0);
        };
    }
};
}
}
