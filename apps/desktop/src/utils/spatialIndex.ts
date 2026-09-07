export interface BoundingBox {
  xmin: number;
  ymin: number;
  xmax: number;
  ymax: number;
}

export interface SpatialItem<T = any> {
  bounds: BoundingBox;
  data: T;
}

/**
 * QuadTree spatial partitioning index for CAD viewport frustum culling.
 * Provides O(log N) spatial range queries for rendering optimization.
 */
export class QuadTree<T = any> {
  private bounds: BoundingBox;
  private capacity: number;
  private maxDepth: number;
  private depth: number;
  private items: SpatialItem<T>[] = [];
  private divided: boolean = false;
  private northWest?: QuadTree<T>;
  private northEast?: QuadTree<T>;
  private southWest?: QuadTree<T>;
  private southEast?: QuadTree<T>;

  constructor(bounds: BoundingBox, capacity: number = 64, maxDepth: number = 8, depth: number = 0) {
    this.bounds = bounds;
    this.capacity = capacity;
    this.maxDepth = maxDepth;
    this.depth = depth;
  }

  public insert(item: SpatialItem<T>): boolean {
    if (!this.intersects(this.bounds, item.bounds)) {
      return false;
    }

    if (this.items.length < this.capacity || this.depth >= this.maxDepth) {
      this.items.push(item);
      return true;
    }

    if (!this.divided) {
      this.subdivide();
    }

    return (
      (this.northWest?.insert(item) ?? false) ||
      (this.northEast?.insert(item) ?? false) ||
      (this.southWest?.insert(item) ?? false) ||
      (this.southEast?.insert(item) ?? false)
    );
  }

  public queryRange(range: BoundingBox, found: T[] = []): T[] {
    if (!this.intersects(this.bounds, range)) {
      return found;
    }

    for (const item of this.items) {
      if (this.intersects(item.bounds, range)) {
        found.push(item.data);
      }
    }

    if (this.divided) {
      this.northWest?.queryRange(range, found);
      this.northEast?.queryRange(range, found);
      this.southWest?.queryRange(range, found);
      this.southEast?.queryRange(range, found);
    }

    return found;
  }

  public clear(): void {
    this.items = [];
    this.divided = false;
    this.northWest = undefined;
    this.northEast = undefined;
    this.southWest = undefined;
    this.southEast = undefined;
  }

  private subdivide(): void {
    const { xmin, ymin, xmax, ymax } = this.bounds;
    const midX = (xmin + xmax) / 2;
    const midY = (ymin + ymax) / 2;
    const nextDepth = this.depth + 1;

    this.northWest = new QuadTree<T>({ xmin, ymin, xmax: midX, ymax: midY }, this.capacity, this.maxDepth, nextDepth);
    this.northEast = new QuadTree<T>({ xmin: midX, ymin, xmax, ymax: midY }, this.capacity, this.maxDepth, nextDepth);
    this.southWest = new QuadTree<T>({ xmin, ymin: midY, xmax: midX, ymax }, this.capacity, this.maxDepth, nextDepth);
    this.southEast = new QuadTree<T>({ xmin: midX, ymin: midY, xmax, ymax }, this.capacity, this.maxDepth, nextDepth);

    this.divided = true;
  }

  private intersects(a: BoundingBox, b: BoundingBox): boolean {
    return !(a.xmax < b.xmin || a.xmin > b.xmax || a.ymax < b.ymin || a.ymin > b.ymax);
  }
}
