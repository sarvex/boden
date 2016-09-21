#include <bdn/init.h>
#include <bdn/win32/TextViewCore.h>

#include <bdn/win32/WindowDeviceContext.h>

namespace bdn
{
namespace win32
{

TextViewCore::TextViewCore(TextView* pOuter)
	: ViewCore(	pOuter, 
				"STATIC",
				pOuter->text().get(),
				SS_NOPREFIX | WS_CHILD,
				0 )
{
}

void TextViewCore::setText(const String& text)
{
	setWindowText(getHwnd(), text);
}

Size TextViewCore::calcPreferredSize(double availableWidth, double availableHeight) const
{
	// note that we ignore availableHeight because there is no way for us to reduce
	// the height of the text. We can only limit the width (by wrapping lines)

    P<TextView> pTextView = cast<TextView>( getOuterViewIfStillAttached() );
	String text;
    if(pTextView!=nullptr)
        text = pTextView->text();

    Size prefSize;

    {
        WindowDeviceContext dc( getHwnd() );

        if(_pFont!=nullptr)
		    dc.setFont( *_pFont );
        prefSize = dc.getTextSize( text, availableWidth );
    }

    Nullable<UiMargin>  pad;
    if(pTextView!=nullptr)
        pad = pTextView->padding();
    UiMargin            uiPadding;
    if(pad.isNull())
    {
        // we should use the "default" padding. This is zero.
        uiPadding = UiMargin(UiLength::sem, 0, 0);
    }
    else
        uiPadding = pad;

	prefSize += uiMarginToDipMargin( uiPadding );	
    
	return prefSize;
}


}
}

