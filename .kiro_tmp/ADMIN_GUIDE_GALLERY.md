# Admin Guide: Managing Homepage Gallery Photos

## Overview
Customers can now upload photos when they write reviews. As an admin, you control which photos appear in the homepage gallery.

## How It Works

### Step 1: Customer Uploads Photo
- Customer completes an order
- Customer writes a review in the mobile app
- Customer can optionally upload a photo with their review
- Photo is automatically approved and saved

### Step 2: Admin Reviews Photos
1. Log in to admin panel
2. Navigate to **Review Management** page
3. You'll see all customer reviews
4. Reviews with photos will show:
   - Customer's photo (displayed in the review card)
   - A button below the photo

### Step 3: Add Photo to Gallery
- Click the **"Add to Gallery"** button on any review with a photo
- Button will turn gold and change to **"Remove from Gallery"**
- Photo immediately appears in the homepage gallery
- No page refresh needed!

### Step 4: Remove Photo from Gallery
- Click the **"Remove from Gallery"** button (gold button)
- Button will turn brown and change back to **"Add to Gallery"**
- Photo is removed from homepage gallery
- Photo is still visible in the review (not deleted)

## Gallery Display Rules

### Homepage Gallery Section
- Shows **8 photos total** in a 4x2 grid
- Featured customer photos appear first (most recent)
- Remaining slots filled with default restaurant images
- If you feature more than 8 photos, only the 8 most recent are shown

### Example Scenarios

**Scenario 1: No Featured Photos**
- Gallery shows 8 default restaurant images

**Scenario 2: 3 Featured Photos**
- Gallery shows 3 customer photos + 5 default images

**Scenario 3: 10 Featured Photos**
- Gallery shows the 8 most recent customer photos
- Older photos are hidden (but still marked as featured)

## Button States

### "Add to Gallery" (Brown Button)
- Photo is NOT in homepage gallery
- Click to add it to gallery

### "Remove from Gallery" (Gold Button)
- Photo IS in homepage gallery
- Click to remove it from gallery

## Tips

1. **Choose High-Quality Photos**: Select clear, well-lit photos that showcase your food and ambiance
2. **Variety**: Mix different types of photos (food, drinks, ambiance, people enjoying meals)
3. **Update Regularly**: Refresh gallery photos periodically to keep content fresh
4. **Monitor Reviews**: Check Review Management page regularly for new customer photos

## Technical Notes

- Photos are stored in: `static/uploads/reviews/`
- Gallery updates instantly (no page refresh needed)
- Photos are never deleted, only hidden/shown in gallery
- All customer photos remain visible in the review itself

## Troubleshooting

**Problem**: Button doesn't respond when clicked
- **Solution**: Check browser console for errors, refresh page

**Problem**: Photo doesn't appear in homepage
- **Solution**: Clear browser cache and refresh homepage

**Problem**: Can't see customer photos
- **Solution**: Make sure customers are using the latest mobile app version

## Color Reference
- Brown button (#8b634b) = Not featured
- Gold button (#c2934d) = Featured
- Matches your site's coffee/brown theme
