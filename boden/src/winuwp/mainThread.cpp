#include <bdn/init.h>
#include <bdn/mainThread.h>

#include <bdn/winuwp/DispatcherAccess.h>

namespace bdn
{	

void CallFromMainThreadBase_::dispatchCall()
{
    BDN_WINUWP_TO_STDEXC_BEGIN;

	P<CallFromMainThreadBase_> pThis = this;


	bdn::winuwp::DispatcherAccess::get().getMainDispatcher()->RunAsync(
		::Windows::UI::Core::CoreDispatcherPriority::Normal,
		ref new Windows::UI::Core::DispatchedHandler(
			[pThis]()
			{
                BDN_WINUWP_TO_PLATFORMEXC_BEGIN

				pThis->call();

                BDN_WINUWP_TO_PLATFORMEXC_END
			} ) );


    BDN_WINUWP_TO_STDEXC_END;

}

void CallFromMainThreadBase_::dispatchCallWhenIdle()
{
    BDN_WINUWP_TO_STDEXC_BEGIN;

	P<CallFromMainThreadBase_> pThis = this;

    bdn::winuwp::DispatcherAccess::get().getMainDispatcher()->RunAsync(
        // using Low priority is correct here. RunAsync only accepts Low and Normal
        // and Low is executed when there are no events pending in the queue.
        // The Idle priority value is apparently not used by CoreDispatcher
		::Windows::UI::Core::CoreDispatcherPriority::Low,
		ref new Windows::UI::Core::DispatchedHandler(
			[pThis]()
			{
                BDN_WINUWP_TO_PLATFORMEXC_BEGIN

				pThis->call();

                BDN_WINUWP_TO_PLATFORMEXC_END
			} ) );

    BDN_WINUWP_TO_STDEXC_END;

}

void CallFromMainThreadBase_::dispatchCallWithDelaySeconds(double seconds)
{
    BDN_WINUWP_TO_STDEXC_BEGIN;

    if(seconds<=0.0000001)
    {
        dispatchCall();
        return;
    }

	struct CallData : public Base
    {
        ~CallData()
        {
            int x=0;
            x++;
        }

        P<ISimpleCallable>                      pCallable;
    };

    P<CallData> pCallData = newObj<CallData>();

    pCallData->pCallable = this;

    ::Windows::Foundation::TimeSpan ts;
    ts.Duration = (int64_t)(seconds*10000000);
    
    // note that we would love to use ::Windows::UI::Xaml::DispatcherTimer here,
    // but unfortunately it does not support setting a priority and the default priority
    // is apparently lower than "normal". That means that timer events only occur when
    // the event queue is empty, which is not good enough for us.
    // So instead we are forced to use a ThreadPoolTimer instead.

    ::Windows::System::Threading::ThreadPoolTimer::CreateTimer(
        ref new ::Windows::System::Threading::TimerElapsedHandler(
            [pCallData](::Windows::System::Threading::ThreadPoolTimer^ pTimer)
            {
                BDN_WINUWP_TO_PLATFORMEXC_BEGIN

                // this handler will be called from another thread, so we must
                // redirect it to the main thread.
                callFromMainThread(
                    [pCallData]()
                    {
                        pCallData->pCallable->call();
                        
                        // we MUST set the callable to null here, so that we can be sure that
                        // it is released from the main thread.
                        // Since the timer handler is called from another thread and the handler holds
                        // a reference to pCallData, the pCallData object will be released from the worker
                        // thread. So if pCallable is not nulled here, it will also get released from that thread.
                        // And that might cause strange problems, especially if the callable references
                        // UI objects.
                        pCallData->pCallable = nullptr;
                    } );

                BDN_WINUWP_TO_PLATFORMEXC_END
            } ),
        ts );

    /*
    pCallData->pTimer = ref new ::Windows::UI::Xaml::DispatcherTimer(); 

    pCallData->pTimer->Interval = ts;

    pCallData->pTimer->Tick += ref new ::Windows::Foundation::EventHandler<::Platform::Object^>(
        [pCallData](::Platform::Object^,::Platform::Object^)
        {
            BDN_WINUWP_TO_PLATFORMEXC_BEGIN

            // only called if not called yet
            if(!pCallData->called)
            {
                pCallData->called = true;

                try
                {
                    pCallData->pTimer->Stop();
                }
                catch(::Platform::Exception^ e)
                {
                    // ignore stop exceptions.
                }

                // release the timer manually. We have a circle reference between the
                // timer and the event handler / call data object. While the garbage collector
                // will eventually collect this, we can make its job easier by breaking the
                // circle.
                pCallData->pTimer = nullptr;

			    pCallData->pCallable->call();
            }

            BDN_WINUWP_TO_PLATFORMEXC_END
        } );

    pCallData->pTimer->Start();
    */

    BDN_WINUWP_TO_STDEXC_END;
}


}

