#include <bdn/init.h>
#include <bdn/ViewTextUi.h>

#include <bdn/ColumnView.h>
#include <bdn/NotImplementedError.h>
#include <bdn/Thread.h>


namespace bdn
{

ViewTextUi::ViewTextUi(IUiProvider* pUiProvider)
{
    _initialized = false;
    _flushPendingScheduled = false;
    _scrollDownPending = false;

    _pUiProvider = pUiProvider;

    if(Thread::isCurrentMain())
    {
        Mutex::Lock lock(_mutex);

        _ensureInitializedWhileMutexLocked();
    }
    else
    {
        P<ViewTextUi> pThis = this;

        asyncCallFromMainThread(
            [this, pThis]()
            {
                Mutex::Lock lock(_mutex);

                _ensureInitializedWhileMutexLocked();
            } );
    }
}

void ViewTextUi::_ensureInitializedWhileMutexLocked()
{
    if(!_initialized)
    {
        _initialized = true;
                
        _pWindow = newObj<Window>(_pUiProvider);

        _pWindow->padding() = UiMargin(10);

        _pScrollView = newObj<ScrollView>();

        _pScrolledColumnView = newObj<ColumnView>();

        _pScrolledColumnView->size().onChange().subscribeParamless( weakMethod(this, &ViewTextUi::scrolledSizeChanged ) );

        _pScrollView->setContentView( _pScrolledColumnView );
    
        _pWindow->setContentView(_pScrollView);

        _pWindow->preferredSizeMinimum() = Size(600, 400);

        _pWindow->visible() = true;

        _pWindow->requestAutoSize();
        _pWindow->requestCenter();
    }
}

P< IAsyncOp<String> > ViewTextUi::readLine()
{
    throw NotImplementedError("ViewTextUi::readLine");
}

    
void ViewTextUi::write(const String& s)
{
    Mutex::Lock lock(_mutex);

    if(Thread::isCurrentMain())
    {
        // we want the ordering of multithreaded writes to be honored.
        // So we have to make sure that any pending writes from other threads
        // are made before we do any writes in the main thread directly.

        _flushPendingWhileMutexLocked();

        _doWriteWhileMutexLocked(s);
    }
    else
    {
        _pendingList.add( s );

        if(!_flushPendingScheduled)
        {
            P<ViewTextUi> pThis = this;

            _flushPendingScheduled = true;
            asyncCallFromMainThread(
                [this, pThis]()
                {                    
                    Mutex::Lock lock( _mutex );
                    _flushPendingWhileMutexLocked();
                } );            
        }
    }
}

void ViewTextUi::_doWriteWhileMutexLocked(const String& s)
{
    _ensureInitializedWhileMutexLocked();

    String remaining = s;
    // normalize linebreaks
    remaining.findAndReplace("\r\n", "\n");

    while(!remaining.isEmpty())
    {
        char32_t separator=0;
        String para = remaining.splitOffToken("\n", true, &separator);

        if(_pCurrParagraphView==nullptr)
        {
            _pCurrParagraphView = newObj<TextView>();
            _pScrolledColumnView->addChildView(_pCurrParagraphView);
        }

        _pCurrParagraphView->text() = _pCurrParagraphView->text().get() + para;

        if(separator!=0)
        {
            // linebreak was found => finish current paragraph.
            _pCurrParagraphView = nullptr;
        }
    }    
}

void ViewTextUi::_flushPendingWhileMutexLocked()
{    
    _flushPendingScheduled = false;

    for( auto& s: _pendingList )
        _doWriteWhileMutexLocked(s);
    _pendingList.clear();
}

void ViewTextUi::writeLine(const String& s)
{
    write(s+"\n");
}


void ViewTextUi::writeError(const String& s)
{
    write(s);
}
	
    
void ViewTextUi::writeErrorLine(const String& s)
{
    writeLine(s);
}


void ViewTextUi::scrolledSizeChanged()
{
    // when the scrolled size has just changed then it may be that the
    // view itself has not yet updates its internal scrolling parameters.
    // So if we scroll down immediately then "all the way down" may not yet
    // reflect the new size.
    // So instead we post this asynchronously to the main thread event queue.
    // That way the scrolling down should happen after the view was updated.

    // if we already have a scroll request pending then we do not need to do schedule
    // another one.    
    if(!_scrollDownPending)
    {
        _scrollDownPending = true;

        // keep ourselves alive.
        P<ViewTextUi> pThis = this;

        asyncCallFromMainThread(
            [pThis, this]()
            {
                 // we want to scroll to the end of the client area.
                // scrollClientRectToVisible supports the infinity value
                // to scroll to the end, so we just use that.
                Rect rect( 0, std::numeric_limits<double>::infinity(), 0, 0 );    

                _scrollDownPending = false;

                _pScrollView->scrollClientRectToVisible(rect);                
            } );   
    }
}

}


