<script type="text/javascript">
<!-- // Protect from our XML parser, which doesn't know to protect <script>
var counting = false;
var count = 0;

function startCountdown(itemID)
{
    counting = true;
    count = 10;
    updateCountdown(itemID)
}

function updateCountdown(itemID)
{
    if (counting)
    {
        count = count - 1;
        if (count >= 0)
        {
            document.getElementById('countdown').innerHTML = count;
            setTimeout('updateCountdown(' + itemID + ')', 1000);
        }
        else
        {
            skipItem(itemID)
        }
    }
}

function playItemExternally(itemID)
{
    counting = false;
    eventURL('action:playItemExternally?itemID=' + itemID)
}

function skipItem(itemID)
{
    counting = false;
    eventURL('action:skipItem?itemID=' + itemID)
}

-->
</script>
