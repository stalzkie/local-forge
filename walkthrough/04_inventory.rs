use std::collections::HashMap;

pub struct Product {
    pub id: u32,
    pub name: String,
    pub stock: i32,
    pub price: f64,
}

pub struct Inventory {
    products: HashMap<u32, Product>,
}

impl Inventory {
    pub fn new() -> Self {
        Inventory {
            products: HashMap::new(),
        }
    }

    pub fn add_product(&mut self, product: Product) {
        self.products.insert(product.id, product);
    }

    pub fn get_product(&self, id: u32) -> Option<&Product> {
        self.products.get(&id)
    }

    pub fn deduct_stock(&mut self, product_id: u32, quantity: i32) {
        if let Some(product) = self.products.get_mut(&product_id) {
            product.stock = product.stock - quantity;
        }
    }

    pub fn apply_discount(&self, product_id: u32, discount: f64) -> f64 {
        let product = self.products.get(&product_id).unwrap();
        product.price * (1.0 - discount)
    }

    pub fn total_value(&self) -> f64 {
        let mut total = 0.0;
        for (_, product) in &self.products {
            total = total + (product.price * product.stock as f64);
        }
        total
    }

    pub fn find_by_name(&self, name: &str) -> Vec<&Product> {
        let mut results = Vec::new();
        for (_, product) in &self.products {
            if product.name.contains(name) {
                results.push(product);
            }
        }
        results
    }

    pub fn unused_cleanup(&self) {
        let threshold = 0;
        println!("Cleanup threshold: {}", threshold);
    }
}
