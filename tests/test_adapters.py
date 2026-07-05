"""Adapter parsing tests using inline HTML/JSON fixtures."""

from __future__ import annotations

import unittest

from scraper.sites.amazon import AmazonAdapter
from scraper.sites.flipkart import FlipkartAdapter
from scraper.sites.meesho import MeeshoAdapter
from scraper.sites.myntra import MyntraAdapter, _extract_js_object, _find_product_list
from scraper.sites.registry import available_sites, get_adapter


class FlipkartProductTest(unittest.TestCase):
    HTML = """
    <div>
      <a href="/cool-phone/p/itm123?pid=ABCD1234"><div>Cool Phone 5G</div></a>
      <div>₹19,999</div>
      <div>4.3 1,234 Ratings &amp; 56 Reviews</div>
    </div>
    """

    def test_parse_products(self) -> None:
        records = FlipkartAdapter().parse_products(self.HTML, "Electronics", "Smartphones", "src", 10)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.site, "flipkart")
        self.assertEqual(record.price, "₹19,999")
        self.assertEqual(record.rating, "4.3")
        self.assertEqual(record.ratings_count, "1,234")
        self.assertEqual(record.reviews_count, "56")
        self.assertEqual(record.product_id, "ABCD1234")
        self.assertIn("Cool Phone", record.title)

    def test_review_url(self) -> None:
        url = FlipkartAdapter().get_reviews_url("https://www.flipkart.com/cool-phone/p/itm123?pid=X")
        self.assertEqual(url, "https://www.flipkart.com/cool-phone/product-reviews/itm123")


class FlipkartReviewTest(unittest.TestCase):
    HTML = """
    <div class="reviewcard">
      <div>
        <div>
          <div class="css-146c3p1">4.0</div>
          <div>Certified Buyer</div>
        </div>
        <div>Great product</div>
        <div>Loved it, works well</div>
        <div>Rahul</div>
        <div>, Delhi</div>
        <div>5 months ago</div>
        <div>Helpful for 12</div>
      </div>
    </div>
    """

    def test_parse_reviews(self) -> None:
        reviews = FlipkartAdapter().parse_reviews(self.HTML, "http://x/p/1", "Cool Phone")
        self.assertEqual(len(reviews), 1)
        review = reviews[0]
        self.assertEqual(review["rating"], 4.0)
        self.assertEqual(review["title"], "Great product")
        self.assertEqual(review["body"], "Loved it, works well")
        self.assertEqual(review["reviewer"], "Rahul")
        self.assertEqual(review["city"], "Delhi")
        self.assertEqual(review["date"], "5 months ago")
        self.assertEqual(review["helpful_count"], 12)


class AmazonTest(unittest.TestCase):
    PRODUCT_HTML = """
    <div data-component-type="s-search-result" data-asin="B0ABCD1234">
      <h2><a href="/dp/B0ABCD1234"><span>Echo Dot 5th Gen</span></a></h2>
      <span class="a-price"><span class="a-offscreen">₹4,499</span></span>
      <span class="a-icon-alt">4.5 out of 5 stars</span>
      <span class="a-size-base s-underline-text">12,345</span>
    </div>
    """

    # Real Amazon review entries are <li data-hook="review"> with the title text
    # prefixed by the star rating.
    REVIEW_HTML = """
    <li data-hook="review">
      <i data-hook="review-star-rating"><span class="a-icon-alt">5.0 out of 5 stars</span></i>
      <a data-hook="review-title"><span>5.0 out of 5 stars</span><span>Excellent value</span></a>
      <span class="a-profile-name">Anita</span>
      <span data-hook="review-body"><span>Battery lasts long and sound is great.</span></span>
      <span data-hook="review-date">Reviewed in India on 5 January 2024</span>
      <span data-hook="helpful-vote-statement">3 people found this helpful</span>
    </li>
    """

    def test_parse_products(self) -> None:
        records = AmazonAdapter().parse_products(self.PRODUCT_HTML, "Electronics", "Speakers", "src", 10)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.product_id, "B0ABCD1234")
        self.assertEqual(record.product_url, "https://www.amazon.in/dp/B0ABCD1234")
        self.assertEqual(record.title, "Echo Dot 5th Gen")
        self.assertEqual(record.price, "₹4,499")
        self.assertEqual(record.rating, "4.5")
        self.assertEqual(record.ratings_count, "12,345")

    def test_parse_reviews(self) -> None:
        reviews = AmazonAdapter().parse_reviews(self.REVIEW_HTML, "http://x", "Echo")
        self.assertEqual(len(reviews), 1)
        review = reviews[0]
        self.assertEqual(review["rating"], "5.0")
        self.assertEqual(review["title"], "Excellent value")
        self.assertEqual(review["body"], "Battery lasts long and sound is great.")
        self.assertEqual(review["reviewer"], "Anita")
        self.assertEqual(review["date"], "5 January 2024")
        self.assertEqual(review["helpful_count"], 3)

    def test_review_url(self) -> None:
        url = AmazonAdapter().get_reviews_url("https://www.amazon.in/dp/B0ABCD1234")
        self.assertEqual(url, "https://www.amazon.in/product-reviews/B0ABCD1234/")


class MyntraTest(unittest.TestCase):
    HTML = """
    <html><body>
    <script>window.__myx = {"searchData":{"results":{"products":[
      {"productId":12345,"product":"Slim Fit T-Shirt","brand":"Roadster",
       "price":499,"rating":4.2,"ratingCount":1500,
       "landingPageUrl":"roadster-slim-tshirt/12345/buy"}
    ]}}};
    var other = 1;
    </script>
    </body></html>
    """

    def test_extract_js_object(self) -> None:
        data = _extract_js_object(self.HTML, "window.__myx")
        self.assertIsNotNone(data)
        products = _find_product_list(data)
        self.assertEqual(len(products), 1)

    def test_parse_products(self) -> None:
        records = MyntraAdapter().parse_products(self.HTML, "Men", "T-Shirts", "src", 10)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.product_url, "https://www.myntra.com/roadster-slim-tshirt/12345/buy")
        self.assertEqual(record.title, "Roadster Slim Fit T-Shirt")
        self.assertEqual(record.price, "₹499")
        self.assertEqual(record.rating, "4.2")
        self.assertEqual(record.ratings_count, "1500")
        self.assertEqual(record.product_id, "12345")

    def test_supports_reviews(self) -> None:
        self.assertTrue(MyntraAdapter().supports_reviews)

    def test_review_url(self) -> None:
        url = MyntraAdapter().get_reviews_url(
            "https://www.myntra.com/casual-shoes/hrx/hrx-shoes/29553912/buy"
        )
        self.assertEqual(url, "https://www.myntra.com/web/v1/reviews/batch/29553912?size=20&page=1")

    def test_build_review_page_url(self) -> None:
        url = MyntraAdapter().build_review_page_url(
            "https://www.myntra.com/web/v1/reviews/batch/29553912?size=20&page=1", 3
        )
        self.assertEqual(url, "https://www.myntra.com/web/v1/reviews/batch/29553912?size=20&page=3")


class MyntraReviewTest(unittest.TestCase):
    # Real responses come back HTML-wrapped: Chromium renders a raw JSON
    # navigation as <html><body><pre>{...}</pre></body></html>.
    HTML = """
    <html><head></head><body><pre>{"reviews":[
      {"id":"r1","userRating":5,"review":"Great fit and comfortable",
       "userName":"Rahul","upvotes":"3","updatedAt":"1735689600000",
       "styleAttribute":[{"name":"Size bought","value":"9"}]}
    ]}</pre></body></html>
    """

    def test_parse_reviews(self) -> None:
        reviews = MyntraAdapter().parse_reviews(self.HTML, "http://x/29553912/buy", "Shoes")
        self.assertEqual(len(reviews), 1)
        review = reviews[0]
        self.assertEqual(review["rating"], 5)
        self.assertEqual(review["body"], "Great fit and comfortable")
        self.assertEqual(review["reviewer"], "Rahul")
        self.assertEqual(review["date"], "2025-01-01")
        self.assertEqual(review["helpful_count"], 3)
        self.assertEqual(review["variant"], "Size bought: 9")

    def test_parse_reviews_empty_payload(self) -> None:
        reviews = MyntraAdapter().parse_reviews(
            '<html><body><pre>{"reviews":[]}</pre></body></html>', "http://x", "Shoes"
        )
        self.assertEqual(reviews, [])


class MeeshoTest(unittest.TestCase):
    DOM_HTML = """
    <html><body>
      <a href="/womens-kurti/p/abc123"><img alt="Trendy Kurti"/> <span>₹399</span></a>
    </body></html>
    """

    NEXT_HTML = """
    <html><body>
      <script id="__NEXT_DATA__" type="application/json">
      {"props":{"pageProps":{"catalogs":[
        {"id":777,"name":"Cotton Saree","slug":"cotton-saree","price":650}
      ]}}}
      </script>
    </body></html>
    """

    def test_parse_products_dom_fallback(self) -> None:
        records = MeeshoAdapter().parse_products(self.DOM_HTML, "Women", "Kurtis", "src", 10)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.product_url, "https://www.meesho.com/womens-kurti/p/abc123")
        self.assertEqual(record.title, "Trendy Kurti")
        self.assertEqual(record.price, "₹399")

    def test_parse_products_next_data(self) -> None:
        records = MeeshoAdapter().parse_products(self.NEXT_HTML, "Women", "Sarees", "src", 10)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.title, "Cotton Saree")
        self.assertEqual(record.price, "₹650")
        self.assertEqual(record.product_id, "777")


class RegistryTest(unittest.TestCase):
    def test_sites_present(self) -> None:
        self.assertEqual(available_sites(), ["flipkart", "amazon", "myntra", "meesho"])

    def test_get_adapter_case_insensitive(self) -> None:
        self.assertEqual(get_adapter("FLIPKART").name, "flipkart")

    def test_unknown_site_raises(self) -> None:
        with self.assertRaises(KeyError):
            get_adapter("ebay")


if __name__ == "__main__":
    unittest.main()
