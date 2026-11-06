export type Listing = {
    provider: string;
    gpu: string;
    hours: number;
    price: number;
};

let listings: Listing[] = [
    { provider: "GPUFarm01", gpu: "H100", hours: 1000, price: 0.5 },
    { provider: "CloudNodeA", gpu: "A100", hours: 500, price: 0.35 },
    { provider: "NodeXYZ", gpu: "4090", hours: 200, price: 0.2 },
    { provider: "EdgeCluster7", gpu: "H100", hours: 1800, price: 0.48 },
    { provider: "ColoMesh", gpu: "A100", hours: 720, price: 0.33 },
];

export function getListings() {
    return listings;
}

export function addListing(listing: Listing) {
    listings = [listing, ...listings];
}
